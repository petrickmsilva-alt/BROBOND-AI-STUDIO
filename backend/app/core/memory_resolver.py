"""MemoryResolver — permanent character identity.

Responsibility: answer "who is this character, exactly?" and refuse to let an
identity change silently. It owns the PERSONA vocabulary and the versioning
rule; it knows nothing about prompts, styles, shots or providers.

Independence: imports `contracts` only. The persistent store is injected
through the `PersonaSource` protocol, so the Core never imports SQLAlchemy and
ETAPA 4 can swap the seed source for PostgreSQL without touching this file.
"""
from __future__ import annotations

from dataclasses import replace

from .contracts import (
    PERSONA_IDENTITY_FIELDS,
    PersonaMemory,
    PersonaSource,
    PersonaStatus,
)


class MemoryError_(RuntimeError):
    """Raised when a memory operation would break identity continuity.

    Named with a trailing underscore to avoid shadowing the builtin
    `MemoryError` for anyone doing `from app.core import *`.
    """


#: Canonical BROBOND characters, seeded from knowledge_base/CHARACTER_LIBRARY.md
#: and backend/app/knowledge.py. Jefferson stays `planned` with no invented
#: attributes: an undefined identity must not be fabricated.
SEED_PERSONAS: tuple[PersonaMemory, ...] = (
    PersonaMemory(
        persona_id="CHAR_PETRICK",
        name="Petrick Martins",
        status=PersonaStatus.APPROVED,
        age=50,
        height_m=1.85,
        body_type="athletic build",
        hair="tied back",
        beard="short beard",
        eyes="dark brown eyes",
        default_style="cinematic realism",
    ),
    PersonaMemory(
        persona_id="CHAR_JEFFERSON",
        name="Jefferson",
        status=PersonaStatus.PLANNED,
    ),
)


class SeedPersonaSource:
    """Default in-memory `PersonaSource`, backed by the canonical seed list."""

    def __init__(self, personas: tuple[PersonaMemory, ...] = SEED_PERSONAS) -> None:
        self._by_id: dict[str, PersonaMemory] = {persona.persona_id: persona for persona in personas}

    def register(self, persona: PersonaMemory) -> PersonaMemory:
        self._by_id[persona.persona_id] = persona
        return persona

    def fetch(self, persona_id: str) -> PersonaMemory | None:
        return self._by_id.get(persona_id)

    def search(self, query: str = "") -> list[PersonaMemory]:
        if not query:
            return list(self._by_id.values())
        needle = query.strip().casefold()
        return [
            persona
            for persona in self._by_id.values()
            if needle in persona.persona_id.casefold() or needle in persona.name.casefold()
        ]


class MemoryResolver:
    """Resolves persona identity and guards its continuity."""

    def __init__(self, source: PersonaSource | None = None) -> None:
        self._source: PersonaSource = source or SeedPersonaSource()

    # ------------------------------------------------------------------ lookup

    def resolve(self, persona_id: str | None) -> PersonaMemory | None:
        """Return the persona for an id, or None when unknown/absent.

        Never raises for a missing persona: an anonymous generation is valid,
        it simply carries no identity block.
        """

        if not persona_id:
            return None
        return self._source.fetch(persona_id)

    def resolve_by_name(self, name: str | None) -> PersonaMemory | None:
        if not name:
            return None
        matches = self._source.search(name.strip())
        return matches[0] if matches else None

    def catalog(self) -> list[PersonaMemory]:
        return self._source.search()

    def is_generable(self, persona_id: str | None) -> bool:
        """Only an approved identity may drive a generation."""

        persona = self.resolve(persona_id)
        return bool(persona and persona.status is PersonaStatus.APPROVED)

    # -------------------------------------------------------------- vocabulary

    def identity_phrase(self, persona: PersonaMemory | None) -> str:
        """Build the PERSONA prompt block for a persona.

        Returns an empty string when there is no usable identity, so the
        PromptCompiler drops the block entirely instead of emitting a stub.
        """

        if persona is None or persona.status is not PersonaStatus.APPROVED:
            return ""
        traits: list[str] = []
        if persona.age is not None:
            traits.append(f"{persona.age} years old")
        if persona.height_m is not None:
            traits.append(f"{persona.height_m:.2f}m tall")
        traits.extend(part for part in (persona.body_type, persona.hair, persona.beard, persona.eyes) if part)
        if not traits:
            return persona.name
        return f"{persona.name}, {', '.join(traits)}"

    def voice_phrase(self, persona: PersonaMemory | None) -> str:
        if persona is None or not persona.voice:
            return ""
        return f"{persona.name} voice: {persona.voice}"

    def default_style(self, persona: PersonaMemory | None) -> str:
        return persona.default_style if persona else ""

    def lora_path(self, persona: PersonaMemory | None) -> str | None:
        """LoRA is resolved from the published persona version, never hardcoded."""

        return persona.lora_path if persona else None

    # -------------------------------------------------------------- governance

    def revise(self, persona: PersonaMemory, *, authorized: bool, **changes: object) -> PersonaMemory:
        """Apply an identity edit, opening a new version.

        A change to face, body, hair, wardrobe or voice without explicit
        authorisation is rejected: identity may never change silently.
        Non-identity fields (LoRA path, reference images, default style) are
        administrative and always allowed.
        """

        identity_changes = {
            name: value
            for name, value in changes.items()
            if name in PERSONA_IDENTITY_FIELDS and getattr(persona, name) != value
        }
        if identity_changes and not authorized:
            fields = ", ".join(sorted(identity_changes))
            raise MemoryError_(
                f"identity change to {persona.name} requires explicit authorization ({fields})"
            )
        unknown = set(changes) - set(PERSONA_IDENTITY_FIELDS) - {"lora_path", "reference_images", "default_style", "status"}
        if unknown:
            raise MemoryError_(f"unknown persona fields: {', '.join(sorted(unknown))}")
        revised = replace(persona, **changes)
        if identity_changes:
            revised = replace(revised, version=persona.version + 1)
        return revised

    def snapshot(self, persona: PersonaMemory) -> dict[str, object]:
        """Immutable memory snapshot attached to an episode or job."""

        return {**persona.to_dict(), "snapshot_of_version": persona.version}
