"""Persona contracts — permanent character identity.

Identity is versioned, never mutated in place: a change to face, body,
hair, wardrobe or voice opens a new version so published episodes keep
their original snapshot. The source protocols are how the Core reads an
identity without knowing SQL exists.

PR010.0 froze this vocabulary. It was moved here verbatim from
`app/core/contracts.py`, which now re-exports it: the objects are the *same*
objects, so `app.core.contracts.PersonaMemory is app.contracts.PersonaMemory`. A module
that needs this vocabulary imports it; it never restates it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

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
class WardrobeItem:
    """One entry of a persona's wardrobe (PR003).

    `metadata` is free-form JSON that the product layer owns (fit, era, colour
    notes...); the Core only carries it, never interprets it.
    """

    name: str
    category: str = ""
    metadata: dict[str, object] = field(default_factory=dict)

@dataclass(frozen=True)
class ReferenceImage:
    """A stored asset a persona points at (PR003).

    The persona *references* an existing asset — it never owns the bytes.
    `image_type` is the product vocabulary: face / body / style / reference.
    """

    asset_id: str
    image_type: str = "reference"
    order_index: int = 0

@dataclass(frozen=True)
class PersonaProfile:
    """The full persistent persona as the Core sees it (PR003).

    `identity` is the existing `PersonaMemory` (the prompt-facing identity,
    versioned as before); the other fields are the product-level data the
    persistent store carries: wardrobe, the LoRA asset that trains this
    persona's look, and the reference images. A source that only knows
    identities (the character ledger) still satisfies this shape with empty
    collections — `MemoryResolver.resolve_persona` guarantees the profile
    exists whenever the persona does.
    """

    identity: PersonaMemory
    wardrobe: tuple[WardrobeItem, ...] = ()
    lora_id: str | None = None
    reference_images: tuple[ReferenceImage, ...] = ()

    @property
    def persona_id(self) -> str:
        return self.identity.persona_id

    @property
    def default_style(self) -> str:
        return self.identity.default_style

    def to_dict(self) -> dict[str, object]:
        return {
            "persona_id": self.persona_id,
            "identity": self.identity.to_dict(),
            "wardrobe": [
                {"name": item.name, "category": item.category, "metadata": dict(item.metadata)}
                for item in self.wardrobe
            ],
            "lora_id": self.lora_id,
            "reference_images": [
                {"asset_id": image.asset_id, "image_type": image.image_type, "order_index": image.order_index}
                for image in self.reference_images
            ],
        }

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
class PersonaProfileSource(Protocol):
    """Where the full persona profile is read from (PR003).

    Kept separate from `PersonaSource` on purpose: the identity protocol is
    ETAPA 4's contract (frozen, implemented by the ledger and the seed
    source) and this one is the richer product view. A source that only
    implements it is a profile source; `MemoryResolver` takes it as an
    optional second injection, so every existing `PersonaSource` keeps
    working unchanged. The Core still never touches SQL: the API layer plugs
    the repository-backed source in.
    """

    def get_profile(self, persona_id: str) -> PersonaProfile | None:
        ...
