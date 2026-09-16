"""PromptCompiler — the only place prompt text is produced.

Responsibility: convert intent + memory + style + shot into an ordered,
structured prompt. Raw user text never reaches a model on its own; it always
becomes the SUBJECT block of a compiled prompt.

Block order is fixed by ETAPA 9 (SUBJECT, PERSONA, ENVIRONMENT, STYLE, CAMERA,
LENS, LIGHT, MOTION, OUTPUT) and extended with CONTINUITY and NEGATIVE so the
same compiler also satisfies the internal structure in SYSTEM_PROMPT.md.

Independence: imports `contracts` only. The compiler receives already-resolved
phrases; it never calls the resolvers itself. That keeps the dependency
direction one-way and makes the compiler trivially testable.
"""
from __future__ import annotations

import re

from collections.abc import Sequence

from .contracts import PROMPT_BLOCK_ORDER, CompiledPrompt, PromptBlocks, SceneBeat


class PromptCompilerError(ValueError):
    """Raised when there is nothing to compile."""


#: Blocks dropped first when the prompt exceeds the provider budget. Subject
#: and persona are dropped last: losing the identity is worse than losing an
#: adjective. `color` sits below `style` on purpose — when a prompt has to be
#: trimmed, the grade is what keeps a sequence recognisable across cuts, so an
#: adjective goes before the palette does.
DROP_PRIORITY: tuple[str, ...] = (
    "continuity",
    "environment",
    "motion",
    "lens",
    "light",
    "camera",
    "style",
    "action",
    "output",
    "color",
    "persona",
    "subject",
)

#: Conservative prompt budget, in characters. PR007 moves model-specific
#: budgets into provider capabilities, so the Core never names a provider brand
#: or catalogue id. A caller may pass an explicit numeric budget resolved by the
#: provider layer; otherwise this safe default is used.
DEFAULT_PROMPT_BUDGET: int = 1000

_WHITESPACE = re.compile(r"\s+")


class PromptCompiler:
    """Deterministic prompt composition.

    Deterministic on purpose: the same inputs always compile to the same
    prompt, so a generation is reproducible and a seed means something. An LLM
    rewriter can be layered on later without changing this contract.
    """

    #: BROBOND quality signature. Preserved verbatim from the pre-Core
    #: PromptEnhancer so existing compiled prompts stay recognisable.
    output_block: str = (
        "detailed textures, natural skin, atmospheric depth, cinematic composition, "
        "high dynamic range, film grain, IMAX quality"
    )

    #: STYLE_GUIDE.md: avoid generic AI aesthetics, oversharpening, plastic
    #: skin. This guard is always present unless explicitly disabled.
    brobond_negative: str = (
        "generic ai look, plastic skin, oversharpened, waxy face, deformed hands, "
        "extra fingers, mutated limbs, watermark, signature, text, logo, lowres, blurry"
    )

    default_style: str = "cinematic realism"
    default_camera: str = "medium shot, 85mm lens, shallow depth of field"
    default_light: str = "soft volumetric light, teal and amber color grade"

    #: Model-side prompt limits vary; trimming is explicit rather than a silent
    #: provider-side truncation.
    max_prompt_chars: int = 1200
    max_negative_chars: int = 600

    # ------------------------------------------------------------------ compile

    def budget_for(self, provider: str | None = None, *, budget: int | None = None) -> int:
        """The character budget under the compiler's own ceiling.

        `provider` remains an accepted opaque argument for backwards-compatible
        callers, but PR007 forbids provider-specific knowledge in the Core. Any
        model-specific value must arrive as the numeric `budget` resolved by the
        provider layer.
        """

        provider_budget = DEFAULT_PROMPT_BUDGET if budget is None else int(budget)
        return min(provider_budget, self.max_prompt_chars)

    def compile(
        self,
        blocks: PromptBlocks,
        *,
        provider: str | None = None,
        budget: int | None = None,
    ) -> CompiledPrompt:
        """Compile structured blocks into the final prompt and negative prompt.

        `provider` is opaque to the Core. `budget` may be supplied by the
        provider registry capabilities; absent that, the conservative default is
        used so existing callers keep working.
        """

        if not blocks.subject.strip():
            raise PromptCompilerError("cannot compile a prompt without a subject")

        emit = dict(blocks.ordered())
        dropped: list[str] = []
        limit = self.budget_for(provider, budget=budget)
        prompt = self._join(emit)
        while len(prompt) > limit:
            victim = next((name for name in DROP_PRIORITY if name in emit and name != "subject"), None)
            if victim is None:
                break
            del emit[victim]
            dropped.append(victim)
            prompt = self._join(emit)

        if len(prompt) > limit:
            prompt = prompt[:limit]

        negative = self.compile_negative(blocks.negative)
        return CompiledPrompt(
            prompt=prompt,
            negative_prompt=negative,
            tokens=self.tokenize(prompt),
            dropped=tuple(dropped),
        )

    def compile_negative(self, extra: str = "", *, include_guard: bool = True) -> str:
        """Assemble the negative prompt: caller terms first, BROBOND guard last."""

        parts = [part for part in (self.normalize(extra), self.brobond_negative if include_guard else "") if part]
        return self._dedupe(", ".join(parts))[: self.max_negative_chars]

    # ------------------------------------------------------------- storyboards

    def compile_beats(
        self,
        beats: Sequence[SceneBeat],
        *,
        brief: str,
        persona: str = "",
        environment: str = "",
        color: str = "",
        style: str = "",
        negative: str = "",
        provider: str | None = None,
        budget: int | None = None,
    ) -> tuple[CompiledPrompt, ...]:
        """Compile a sequence of beats into one prompt per scene.

        This is the consumer `StoryboardEngine.as_beats` was built for: the
        storyboard casts real shots, and here each cast beat becomes a prompt
        whose ACTION, CAMERA, LENS, LIGHT and CONTINUITY come from the preset
        rather than from a placeholder.

        The signature takes `SceneBeat`, a contract type, on purpose — the
        compiler imports `contracts` and nothing else, so it cannot know what a
        `Storyboard` is. Independence is a guarded invariant
        (`test_core_independence.py`), not a convention.

        `persona`, `color` and `style` are passed in already resolved: the
        compiler never calls a resolver.
        """

        return tuple(
            self.compile(
                PromptBlocks(
                    subject=self.normalize(brief),
                    persona=self.normalize(persona),
                    environment=self.normalize(environment),
                    action=self.normalize(beat.reference),
                    camera=self.normalize(beat.camera),
                    lens=self.normalize(beat.lens),
                    light=self.normalize(beat.lighting),
                    color=self.normalize(color),
                    motion=self.normalize(beat.motion),
                    style=self.normalize(style),
                    continuity=self.normalize(beat.continuity),
                    output=self.output_block,
                    negative=negative,
                ),
                provider=provider,
                budget=budget,
            )
            for beat in beats
        )

    # ------------------------------------------------------------------- facade

    def enhance(
        self,
        prompt: str,
        style: str | None = None,
        persona: str | None = None,
        camera: str | None = None,
        lighting: str | None = None,
        continuity: str | None = None,
        environment: str | None = None,
        motion: str | None = None,
        lens: str | None = None,
        negative_prompt: str = "",
    ) -> str:
        """Backward-compatible single-string entry point.

        Signature and defaults match the pre-Core `PromptEnhancer.enhance`, so
        `/api/v1/prompts/enhance` and the storyboard expansion keep their
        behaviour while the composition now happens in the Core.
        """

        return self.build(
            prompt,
            style=style,
            persona=persona,
            camera=camera,
            lighting=lighting,
            continuity=continuity,
            environment=environment,
            motion=motion,
            lens=lens,
            negative_prompt=negative_prompt,
        ).prompt

    def build(
        self,
        prompt: str,
        style: str | None = None,
        persona: str | None = None,
        camera: str | None = None,
        lighting: str | None = None,
        continuity: str | None = None,
        environment: str | None = None,
        motion: str | None = None,
        lens: str | None = None,
        negative_prompt: str = "",
    ) -> CompiledPrompt:
        """Fill the blocks with defaults and compile."""

        return self.compile(
            PromptBlocks(
                subject=self.normalize(prompt),
                persona=self.normalize(persona or ""),
                environment=self.normalize(environment or ""),
                style=self.normalize(style or self.default_style),
                camera=self.normalize(camera or self.default_camera),
                lens=self.normalize(lens or ""),
                light=self.normalize(lighting or self.default_light),
                motion=self.normalize(motion or ""),
                continuity=self.normalize(continuity or ""),
                output=self.output_block,
                negative=negative_prompt,
            )
        )

    # ------------------------------------------------------------------- helpers

    @staticmethod
    def tokenize(prompt: str) -> tuple[str, ...]:
        """Split a compiled prompt into its clause tokens.

        Matches the `tokens` field the API already returned, so the contract
        stays stable now that composition moved into the Core.
        """

        return tuple(part.strip() for part in prompt.split(", ") if part.strip())

    @staticmethod
    def normalize(value: str) -> str:
        """Normalise whitespace and strip trailing punctuation from a block.

        Public because GenerationSpecBuilder needs the exact same normalisation
        the compiler applies internally, so a subject built outside the
        compiler cannot differ from one built inside it.
        """

        collapsed = _WHITESPACE.sub(" ", value or "").strip()
        return collapsed.rstrip(".").strip()


    @classmethod
    def _join(cls, blocks: dict[str, str]) -> str:
        """Concatenate the blocks in emission order, without repeating a clause.

        The dedupe is not cosmetic. `ShotResolver.camera_phrase` already appends
        the preset's focal length and `lens_phrase` starts with it, so every
        compiled prompt that carries a shot preset used to emit the focal twice
        ("..., 35mm, 35mm, ..."). `_dedupe` existed but was only ever applied to
        the negative prompt.
        """

        joined = ", ".join(
            blocks[name] for name in PROMPT_BLOCK_ORDER if name in blocks and blocks[name]
        )
        return cls._dedupe(joined)

    @staticmethod
    def _dedupe(value: str) -> str:
        """Remove repeated clauses, case-insensitively, keeping first order."""

        kept: list[str] = []
        lowered: set[str] = set()
        for part in (item.strip() for item in value.split(",")):
            if part and part.casefold() not in lowered:
                lowered.add(part.casefold())
                kept.append(part)
        return ", ".join(kept)
