"""BROBOND CORE contracts.

Vocabulary only: frozen dataclasses, enums and protocols. This module imports
nothing from the rest of the package, which is what allows every Core component
(`MemoryResolver`, `StyleResolver`, `ShotResolver`, `PromptCompiler`,
`DirectorAgent`, `GenerationSpecBuilder`) to be imported, instantiated and
tested on its own.

Rule enforced here: a contract never decides anything. Behaviour lives in the
component that owns that vocabulary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable
from uuid import uuid4

#: Version of the GenerationSpec shape. Bump when a mandatory field is added,
#: removed or re-typed so persisted specs stay interpretable.
SPEC_SCHEMA_VERSION = "1.0"

#: The 19 mandatory GenerationSpec fields, declared once. Every producer and
#: consumer of a spec imports this tuple instead of restating the list, so the
#: contract cannot drift between the Core, the API schemas and the providers.
GENERATION_SPEC_FIELDS: tuple[str, ...] = (
    "project_id",
    "user_id",
    "persona_id",
    "style_id",
    "prompt_original",
    "prompt_compiled",
    "negative_prompt",
    "camera",
    "lens",
    "lighting",
    "motion",
    "weather",
    "aspect_ratio",
    "fps",
    "duration",
    "provider",
    "seed",
    "lora",
    "controlnet",
)

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


#: PersonaMemory attributes whose silent mutation would break identity
#: continuity. Changing any of them requires explicit authorisation and opens
#: a new version (SYSTEM_PROMPT.md, "Memória").
PERSONA_IDENTITY_FIELDS: tuple[str, ...] = (
    "name",
    "age",
    "height_m",
    "body_type",
    "hair",
    "beard",
    "eyes",
    "voice",
    "wardrobe",
)


class GenerationKind(str, Enum):
    """What the spec is meant to produce. Providers branch on this, never on
    free-form strings."""

    IMAGE = "image"
    VIDEO = "video"


class PersonaStatus(str, Enum):
    """A persona may only drive generation once its identity is approved."""

    PLANNED = "planned"
    APPROVED = "approved"
    RETIRED = "retired"


@dataclass(frozen=True)
class PersonaMemory:
    """Permanent character identity.

    Mirrors the ETAPA 4 field list. Identity is versioned: any change to face,
    body, hair, wardrobe or voice creates a new version rather than mutating
    the previous one, so already-published episodes keep their original memory
    snapshot (SYSTEM_PROMPT.md, "Memória").
    """

    persona_id: str
    name: str
    status: PersonaStatus = PersonaStatus.APPROVED
    age: int | None = None
    height_m: float | None = None
    body_type: str = ""
    hair: str = ""
    beard: str = ""
    eyes: str = ""
    voice: str = ""
    wardrobe: str = ""
    default_style: str = ""
    lora_path: str | None = None
    reference_images: tuple[str, ...] = ()
    version: int = 1

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["reference_images"] = list(self.reference_images)
        return payload


@dataclass(frozen=True)
class StylePreset:
    """A cinematic library entry (ETAPA 5).

    The user picks a style; the style carries the whole technical vocabulary so
    nobody has to type a prompt.
    """

    style_id: str
    name: str
    lens: str
    lut: str
    lighting: str
    contrast: str
    grain: str
    camera_motion: str
    particles: str
    fps: int
    palette: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ShotPreset:
    """A shot library entry (ETAPA 6).

    A shot is a reusable direction preset, not a prompt blob
    (knowledge_base/SHOT_LIBRARY.md).
    """

    code: str
    name: str
    camera_path: str
    speed: str
    lens: str
    focus: str
    shake: str
    depth: str
    intention: str = ""
    # ETAPA 6 — knowledge_base/SHOT_LIBRARY.md "Expansion policy": "New shots
    # require code, name, lens, frame, movement, lighting, emotional intention
    # and continuity notes." Added with defaults so the ten published presets
    # keep constructing unchanged.
    frame: str = ""
    lighting: str = ""
    continuity: str = ""
    family: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SceneBeat:
    """One directed scene, produced by the DirectorAgent.

    Carries narrative intent and camera language, never a compiled prompt: the
    PromptCompiler owns text, the Director owns meaning.
    """

    number: int
    objective: str
    emotion: str
    camera: str
    lighting: str
    motion: str
    duration_seconds: float = 5.0
    shot_code: str | None = None
    reference: str = ""
    #: Filled by StoryboardEngine.as_beats when the beat has a shot cast into
    #: it (ETAPA 9). Empty for an uncast beat, so the Director's own beats are
    #: unaffected and the prompt simply omits the block.
    lens: str = ""
    continuity: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DirectorIntent:
    """The Director's answer to a plain-language request.

    This is the object a user-facing conversation ends with: concept, script,
    scenes, cameras, music and duration. No technical prompt is ever exposed.
    """

    intent: str
    concept: str
    format: str
    logline: str
    script: str
    beats: tuple[SceneBeat, ...]
    camera_language: str
    lighting_language: str
    music: str
    pacing: str
    style_hint: str
    duration_seconds: float
    #: Short direction question, filled only when the intention could follow
    #: more than one language. SYSTEM_PROMPT.md: "faça uma pergunta curta de
    #: direção". Empty means the director is confident.
    clarification: str = ""

    @property
    def scene_count(self) -> int:
        return len(self.beats)

    @property
    def needs_direction(self) -> bool:
        return bool(self.clarification)

    def to_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "concept": self.concept,
            "format": self.format,
            "logline": self.logline,
            "script": self.script,
            "beats": [beat.to_dict() for beat in self.beats],
            "camera_language": self.camera_language,
            "lighting_language": self.lighting_language,
            "music": self.music,
            "pacing": self.pacing,
            "style_hint": self.style_hint,
            "duration_seconds": self.duration_seconds,
            "scene_count": self.scene_count,
            "clarification": self.clarification,
        }


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


@dataclass(frozen=True)
class GenerationSpec:
    """The single object a provider receives (ETAPA 3).

    Providers never receive loose strings: every decision the Core made is
    carried here, versioned and traceable.
    """

    prompt_original: str
    prompt_compiled: str
    project_id: str | None = None
    user_id: str | None = None
    persona_id: str | None = None
    style_id: str | None = None
    negative_prompt: str = ""
    camera: str = ""
    lens: str = ""
    lighting: str = ""
    motion: str = ""
    weather: str = ""
    aspect_ratio: str = "16:9"
    fps: int = 24
    duration: float = 5.0
    provider: str = "flux-dev"
    seed: int | None = None
    lora: str | None = None
    controlnet: str = "none"
    # -----------------------------------------------------------------------
    # Extra fields beyond the 19 mandatory ones.
    #
    # `GENERATION_SPEC_FIELDS` is the contract and stays at 19. These extras
    # exist because ETAPA 3 forbids a provider from receiving anything but the
    # spec: sampling parameters and resolved runtime paths therefore live here,
    # typed, instead of arriving as a loose `parameters` dict.
    # -----------------------------------------------------------------------
    #: Sampling. Typed defaults match the pre-spec `ImageGenerationRequest`.
    resolution: int = 1024
    guidance_scale: float = 7.5
    steps: int = 28
    ip_adapter_scale: float = 0.7
    #: Video mode and switches. Ignored by image providers.
    mode: str = "text-to-video"
    cinematic_mode: bool = True
    slow_motion: bool = False
    native_audio: bool = False
    #: Resolved local path of the IP-Adapter reference image. `controlnet` names
    #: the mode; this names the file. The worker resolves it from an Asset after
    #: validating workspace ownership.
    reference_path: str | None = None
    kind: GenerationKind = GenerationKind.IMAGE
    spec_id: str = field(default_factory=lambda: uuid4().hex)
    schema_version: str = SPEC_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        return payload

    def trace(self) -> str:
        """Short human-readable handle for logs and job records."""

        return f"{self.spec_id[:8]}:{self.provider}:{self.style_id or 'no-style'}"


@runtime_checkable
class PersonaSource(Protocol):
    """Where persona identity is read from.

    The Core depends on this protocol, not on SQLAlchemy. The API layer plugs
    the persistent store in (ETAPA 4) without the Core knowing about it.
    """

    def fetch(self, persona_id: str) -> PersonaMemory | None:
        ...

    def search(self, query: str = "") -> list[PersonaMemory]:
        ...


@runtime_checkable
class StyleSource(Protocol):
    def fetch(self, style_id: str) -> StylePreset | None:
        ...

    def search(self, query: str = "") -> list[StylePreset]:
        ...


@runtime_checkable
class ShotSource(Protocol):
    def fetch(self, code: str) -> ShotPreset | None:
        ...

    def search(self, query: str = "") -> list[ShotPreset]:
        ...


@runtime_checkable
class LanguageModel(Protocol):
    """Optional LLM hook for the DirectorAgent.

    Nothing in the Core pretends a model is loaded: when no implementation is
    injected the Director stays deterministic and says so.
    """

    def complete(self, instruction: str, context: str) -> str:
        ...
