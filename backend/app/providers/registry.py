"""Provider registry — the single source of truth for which adapter runs.

ETAPA 10. Before this, adapter selection was this branch in the worker:

    if job.type == GenerationType.IMAGE:
        provider = FluxDiffusersProvider(...)   # whatever spec.provider said
    else:
        provider = WanVideoProvider(...)        # whatever spec.provider said

So `SYSTEM_PROMPT.md`'s "adapters substituíveis" was not actually true: there
was no way to substitute one. Measured consequences:

    resolve_model_id("wan-video",      FLUX) -> "black-forest-labs/FLUX.1-dev"
    resolve_model_id("hunyuan-video",  WAN)  -> "wan-2.1-t2v"

Asking for Hunyuan returned Wan with no error, and `GET /api/v1/models/video`
already advertised `hunyuan-video` as `planned-provider` with nothing behind it.

This registry makes the choice explicit and refuses the combinations it cannot
honour, instead of quietly running a different model than the one requested.

Classes are resolved **at call time** through `getattr` on the module. That is
not incidental: the worker tests monkeypatch
`app.providers.image.FluxDiffusersProvider`, and an early-bound reference would
defeat the patch.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field

from ..core.contracts import GenerationKind


class ProviderNotFound(KeyError):
    """No adapter is registered for this provider id."""


class ProviderUnavailable(RuntimeError):
    """The provider is registered but cannot run — planned, remote-only, or wrong kind."""


#: A provider that has a local diffusers adapter in this repository.
STATUS_LOCAL = "local-provider"

#: Advertised, but served by an external API rather than a local pipeline.
STATUS_REMOTE = "remote-provider"

#: Advertised, but no adapter exists yet. Refused explicitly, never silently
#: substituted with another model.
STATUS_PLANNED = "planned-provider"


@dataclass(frozen=True)
class ProviderEntry:
    """One row of the registry.

    `module` and `attribute` name the adapter instead of holding it, so the
    registry never imports a provider at module scope and a test can still
    monkeypatch the class.
    """

    provider_id: str
    label: str
    kind: GenerationKind
    status: str
    model_id: str = ""
    module: str = ""
    attribute: str = ""
    #: Conditioning modes this adapter can honour, e.g. ("ip-adapter",).
    conditioning: tuple[str, ...] = ()
    #: Spec fields the adapter consumes. Mirrors the adapter's own declaration
    #: so the catalogue can be checked against it.
    consumed: tuple[str, ...] = field(default=())

    @property
    def runnable(self) -> bool:
        """Whether a local adapter exists for this entry."""

        return self.status == STATUS_LOCAL and bool(self.module and self.attribute)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.provider_id,
            "label": self.label,
            "kind": self.kind.value,
            "status": self.status,
            "model_id": self.model_id,
            "conditioning": list(self.conditioning),
        }


#: Catalogue ids, matching `GET /api/v1/models/image` and `/models/video`.
#: The ids are the ones the API already advertises — this registry does not
#: invent new ones.
REGISTRY: dict[str, ProviderEntry] = {
    entry.provider_id: entry
    for entry in (
        ProviderEntry(
            provider_id="flux-dev",
            label="FLUX.1 Dev",
            kind=GenerationKind.IMAGE,
            status=STATUS_LOCAL,
            model_id="black-forest-labs/FLUX.1-dev",
            module="app.providers.image",
            attribute="FluxDiffusersProvider",
            conditioning=("ip-adapter",),
        ),
        ProviderEntry(
            provider_id="flux-1.1-pro-ultra",
            label="Flux 1.1 Pro Ultra",
            kind=GenerationKind.IMAGE,
            status=STATUS_REMOTE,
        ),
        ProviderEntry(
            provider_id="wan-2.1-t2v",
            label="Wan 2.1 Text to Video",
            kind=GenerationKind.VIDEO,
            status=STATUS_LOCAL,
            model_id="Wan-AI/Wan2.1-T2V-1.3B-Diffusers",
            module="app.providers.video",
            attribute="WanVideoProvider",
        ),
        ProviderEntry(
            provider_id="hunyuan-video",
            label="Hunyuan Video",
            kind=GenerationKind.VIDEO,
            status=STATUS_LOCAL,
            model_id="hunyuanvideo-community/HunyuanVideo",
            module="app.providers.video",
            attribute="HunyuanVideoProvider",
        ),
    )
}

#: What to run when a job does not name a provider, per kind.
DEFAULTS: dict[GenerationKind, str] = {
    GenerationKind.IMAGE: "flux-dev",
    GenerationKind.VIDEO: "wan-2.1-t2v",
}


def register(entry: ProviderEntry) -> None:
    """Add or replace an entry.

    This is the extension point `SYSTEM_PROMPT.md` asks for: a future provider
    is one registration, not another branch in the worker.
    """

    REGISTRY[entry.provider_id] = entry


def unregister(provider_id: str) -> None:
    REGISTRY.pop(provider_id, None)


def lookup(provider_id: str | None) -> ProviderEntry | None:
    """The entry for an id, or `None`. Never raises, never invents."""

    if not provider_id:
        return None
    return REGISTRY.get(provider_id)


def resolve(provider_id: str | None, kind: GenerationKind) -> ProviderEntry:
    """The entry that should run, falling back to the kind's default.

    A repository-style id (`"org/model"`) is not a catalogue id, so it falls
    back rather than being treated as a provider name.
    """

    entry = lookup(provider_id)
    if entry is not None:
        return entry
    return REGISTRY[DEFAULTS[kind]]


def ids(kind: GenerationKind | None = None) -> tuple[str, ...]:
    """Registered ids, optionally filtered by kind."""

    return tuple(
        provider_id
        for provider_id, entry in REGISTRY.items()
        if kind is None or entry.kind is kind
    )


def describe(kind: GenerationKind | None = None) -> tuple[dict[str, object], ...]:
    """The catalogue, in registry order."""

    return tuple(REGISTRY[provider_id].to_dict() for provider_id in ids(kind))


def check(entry: ProviderEntry, kind: GenerationKind) -> None:
    """Refuse a combination that cannot run, with a reason.

    Called before anything is loaded. A planned provider must fail loudly:
    silently running a different model is how a user ends up with output from
    the wrong pipeline and no explanation.
    """

    if entry.status == STATUS_PLANNED:
        raise ProviderUnavailable(f"provider '{entry.provider_id}' is planned and has no adapter yet")
    if entry.status == STATUS_REMOTE:
        raise ProviderUnavailable(
            f"provider '{entry.provider_id}' is served by a remote API and has no local adapter"
        )
    if not entry.runnable:
        raise ProviderUnavailable(f"provider '{entry.provider_id}' has no local adapter")
    if entry.kind is not kind:
        raise ProviderUnavailable(
            f"provider '{entry.provider_id}' is a {entry.kind.value} adapter, "
            f"but this job needs {kind.value}"
        )


def adapter_class(entry: ProviderEntry):
    """The adapter class, resolved at call time.

    Late binding is required: tests monkeypatch the class on its module, and an
    early reference would keep pointing at the real one.
    """

    module = importlib.import_module(entry.module)
    try:
        return getattr(module, entry.attribute)
    except AttributeError as error:  # pragma: no cover - registry/code drift
        raise ProviderUnavailable(
            f"provider '{entry.provider_id}' names {entry.module}.{entry.attribute}, which does not exist"
        ) from error


def build(
    provider_id: str | None,
    kind: GenerationKind,
    *,
    model_id: str | None = None,
):
    """Instantiate the adapter for `provider_id`.

    `model_id` overrides the entry's default, which is how a caller pins a
    specific checkpoint without adding a registry row.
    """

    entry = resolve(provider_id, kind)
    check(entry, kind)
    return adapter_class(entry)(model_id=model_id or entry.model_id)
