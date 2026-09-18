"""Prompt contracts — the block structure a prompt is built from.

Raw user text never reaches a model. It is decomposed into the thirteen
blocks `SYSTEM_PROMPT.md` declares, emitted in a fixed order, and only the
`PromptCompiler` turns them into text.

PR010.0 froze this vocabulary. It was moved here verbatim from
`app/core/contracts.py`, which now re-exports it: the objects are the *same*
objects, so `app.core.contracts.PromptBlocks is app.contracts.PromptBlocks`. A module
that needs this vocabulary imports it; it never restates it.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Prompt block order, aligned in ETAPA 9 with the thirteen blocks that
#: SYSTEM_PROMPT.md ("Estrutura de prompt interno") declares. The two blocks that
#: were missing until then — ACTION and COLOR — are now emitted, and STYLE moved
#: to its declared position (after MOTION, as a global look modifier rather than
#: the fourth thing the model reads).
PROMPT_BLOCK_ORDER: tuple[str, ...] = (
    "subject",
    "persona",
    "environment",
    "action",
    "camera",
    "lens",
    "light",
    "color",
    "motion",
    "style",
    "continuity",
    "output",
)

#: NEGATIVE is the thirteenth block in SYSTEM_PROMPT.md. It is declared here but
#: kept out of `PROMPT_BLOCK_ORDER` on purpose: diffusion providers take the
#: negative prompt as a separate argument, so appending it to the positive prompt
#: would invert its meaning.
NEGATIVE_BLOCK: str = "negative"

#: All thirteen blocks the internal structure declares, in document order.
PROMPT_BLOCKS: tuple[str, ...] = (*PROMPT_BLOCK_ORDER, NEGATIVE_BLOCK)

@dataclass
class PromptBlocks:
    """Structured prompt blocks. Raw user text never reaches a model as-is."""

    subject: str = ""
    persona: str = ""
    environment: str = ""
    #: What happens in the scene. Distinct from CAMERA (how it is filmed) and
    #: from MOTION (how the camera moves). Added in ETAPA 9.
    action: str = ""
    style: str = ""
    camera: str = ""
    lens: str = ""
    light: str = ""
    #: Grade, palette, contrast and grain. Split out of STYLE in ETAPA 9 so a
    #: prompt over budget can drop adjectives and keep the colour identity.
    color: str = ""
    motion: str = ""
    continuity: str = ""
    output: str = ""
    negative: str = ""

    def ordered(self) -> list[tuple[str, str]]:
        """Blocks in emission order, empties dropped."""

        return [(name, getattr(self, name).strip()) for name in PROMPT_BLOCK_ORDER if getattr(self, name).strip()]

    def to_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in PROMPT_BLOCKS}

@dataclass(frozen=True)
class CompiledPrompt:
    """Result of compiling PromptBlocks: what the provider will receive."""

    prompt: str
    negative_prompt: str
    tokens: tuple[str, ...] = ()
    #: Blocks dropped to respect the provider character budget, lowest
    #: priority first. Recorded so a trimmed prompt is never silent.
    dropped: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "tokens": list(self.tokens),
            "dropped": list(self.dropped),
        }
