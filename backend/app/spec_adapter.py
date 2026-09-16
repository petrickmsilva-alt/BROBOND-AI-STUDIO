"""Translate a persisted Job into a GenerationSpec.

Why this module exists: ETAPA 3 requires every provider to receive *only* a
`GenerationSpec`. The worker therefore has to turn a queued `Job` into one
before calling a provider. That translation is **transport adaptation**, not a
creative decision — every decision (style, persona, prompt, camera, lens) is
still made by the Core. So the mapping lives here, at the boundary, and the
Core keeps not knowing that `app.schemas.Job` exists.

Layering:
    app.schemas.Job  --(this module)-->  GenerationSpecBuilder  -->  GenerationSpec  -->  provider
"""
from __future__ import annotations

from .core.contracts import GenerationKind, GenerationSpec
from .core.generation_spec_builder import BuildResult, GenerationSpecBuilder

#: Camera motions that mean "no direction given" rather than "hold the camera".
#: Mapping the default `"static"` onto the spec would override a style's own
#: camera motion on every video job, which is not what the caller asked for.
NEUTRAL_CAMERA_MOTIONS: frozenset[str] = frozenset({"", "static", "none"})

#: Catalogue ids exposed by `GET /api/v1/models/image` mapped onto loadable
#: model ids. Anything already shaped like a repository id passes through; an
#: unknown catalogue id falls back instead of inventing a repository.
IMAGE_MODEL_IDS: dict[str, str] = {
    "flux-dev": "black-forest-labs/FLUX.1-dev",
}

DEFAULT_IMAGE_PROVIDER = "flux-dev"
DEFAULT_VIDEO_PROVIDER = "wan-2.1-t2v"


def resolve_model_id(provider: str | None, fallback: str) -> str:
    """Map a provider identifier onto something a worker can load."""

    if not provider:
        return fallback
    if provider in IMAGE_MODEL_IDS:
        return IMAGE_MODEL_IDS[provider]
    if "/" in provider:  # already a repository-style id
        return provider
    return fallback


def job_kind(job) -> GenerationKind:
    """Read the generation kind off a job.

    Handles both the enum and a plain string. `str()` on a `str, Enum` member
    yields `"GenerationType.VIDEO"` rather than `"video"`, so the member's
    `.value` is unwrapped explicitly — comparing the `str()` of the enum would
    silently classify every video job as an image.
    """

    raw = getattr(job, "type", GenerationKind.IMAGE)
    value = getattr(raw, "value", raw)
    return GenerationKind.VIDEO if str(value) == "video" else GenerationKind.IMAGE


def compile_job(job, resolver: GenerationSpecBuilder | None = None) -> BuildResult:
    """Build the `GenerationSpec` a provider will receive for `job`.

    Accepts anything shaped like `app.schemas.Job` (duck-typed on purpose, so
    this module is unit-testable without importing the API layer).
    """

    builder = resolver or GenerationSpecBuilder()
    parameters: dict = dict(getattr(job, "parameters", None) or {})

    if job_kind(job) is GenerationKind.VIDEO:
        kwargs = _video_kwargs(job, parameters)
    else:
        kwargs = _image_kwargs(job, parameters)

    return builder.build_traced(**kwargs)


def spec_from_job(job, resolver: GenerationSpecBuilder | None = None) -> GenerationSpec:
    """Convenience wrapper when the resolution trace is not needed."""

    return compile_job(job, resolver).spec


# --------------------------------------------------------------------- mappings


def _shared_kwargs(job, parameters: dict) -> dict:
    """Fields both generation kinds carry."""

    return {
        "prompt": getattr(job, "prompt", "") or "",
        "kind": job_kind(job),
        # The workspace is the tenant this job belongs to; the request schemas
        # have no project field yet, so it is carried as the owning principal.
        "user_id": parameters.get("workspace_id"),
        "project_id": parameters.get("project_id"),
        "aspect_ratio": parameters.get("aspect_ratio") or "16:9",
        "seed": parameters.get("seed"),
        # `style`, `persona_id` and `shot` are not part of the generation
        # request schemas yet; until the UX exposes them (ETAPA 15) the Core
        # falls back to its own defaults, which is the documented precedence.
        "style": parameters.get("style"),
        "persona_id": parameters.get("persona_id"),
        # PR004: the studio may narrow the persona wardrobe block to the
        # items the project selected (names as stored on the persona).
        "wardrobe": parameters.get("wardrobe"),
        "shot": parameters.get("shot"),
        "weather": parameters.get("weather") or "",
        "camera": _camera(parameters),
        "negative_prompt": parameters.get("negative_prompt") or "",
    }


def _image_kwargs(job, parameters: dict) -> dict:
    return {
        **_shared_kwargs(job, parameters),
        "provider": resolve_model_id(parameters.get("model"), DEFAULT_IMAGE_PROVIDER),
        "resolution": parameters.get("resolution") or 1024,
        "guidance_scale": parameters.get("guidance_scale"),
        "steps": parameters.get("steps"),
        "ip_adapter_scale": parameters.get("ip_adapter_scale"),
        "controlnet": parameters.get("controlnet") or "none",
        # The worker validates ownership and replaces these with resolved paths
        # before the provider sees the spec.
        "lora": parameters.get("lora_id"),
    }


def _video_kwargs(job, parameters: dict) -> dict:
    return {
        **_shared_kwargs(job, parameters),
        "provider": resolve_model_id(parameters.get("model"), DEFAULT_VIDEO_PROVIDER),
        "mode": parameters.get("mode") or "text-to-video",
        "fps": parameters.get("fps"),
        "duration": parameters.get("duration_seconds") or 5.0,
        # PR009: the Wan connector consumes motion magnitude from the spec.
        "motion_strength": parameters.get("motion_strength"),
        "cinematic_mode": bool(parameters.get("cinematic_mode", True)),
        "slow_motion": bool(parameters.get("slow_motion", False)),
        "native_audio": bool(parameters.get("native_audio", False)),
        "lora": parameters.get("lora_id"),
    }


def _camera(parameters: dict) -> str | None:
    motion = parameters.get("camera_motion")
    if motion is None or str(motion).strip().casefold() in NEUTRAL_CAMERA_MOTIONS:
        return None
    return str(motion)
