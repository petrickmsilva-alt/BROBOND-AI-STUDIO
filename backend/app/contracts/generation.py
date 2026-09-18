"""Generation contracts — what a provider is asked to produce.

`GenerationSpec` is the product's spine (ETAPA 3): the single object every
provider receives. Nothing else crosses that boundary — no loose prompt
string, no `parameters` dict. `GENERATION_SPEC_FIELDS` is the mandatory
field list, declared once so producers and consumers cannot drift.

PR010.0 froze this vocabulary. It was moved here verbatim from
`app/core/contracts.py`, which now re-exports it: the objects are the *same*
objects, so `app.core.contracts.GenerationSpec is app.contracts.GenerationSpec`. A module
that needs this vocabulary imports it; it never restates it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
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

class GenerationKind(str, Enum):
    """What the spec is meant to produce. Providers branch on this, never on
    free-form strings."""

    IMAGE = "image"
    VIDEO = "video"

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
    provider: str = ""
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
    #: PR009: motion magnitude the video connector should aim for. A pipeline
    #: that has no such control filters it out at call time, the same way
    #: guidance-distilled image pipelines drop `negative_prompt`. Travels
    #: inside the spec because a provider may receive nothing else.
    motion_strength: float = 1.0
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
