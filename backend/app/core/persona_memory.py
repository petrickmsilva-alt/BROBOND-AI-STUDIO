"""Persona Memory Engine — permanent, versioned, governed character identity.

ETAPA 4. `MemoryResolver` (ETAPA 2) answers *"who is this character?"* and
knows the versioning **rule**. It does not keep history: `revise()` returned a
persona with `version + 1` and the previous identity was simply dropped, which
made the CHARACTER_LIBRARY rule — *"existing episodes keep their original memory
snapshot"* — impossible to honour, because nothing recorded a snapshot.

This module supplies the missing half, and only the missing half:

    PersonaLedger         append-only version history (implements PersonaSource)
    PersonaMemoryEngine   governance (create/revise/approve/retire), episode
                          snapshots and drift reporting

Both **compose** `MemoryResolver`: identity vocabulary and the identity-change
rule stay in ETAPA 2's file, so there is exactly one definition of each. The
ledger implements `PersonaSource`, which is the seam `memory_resolver.py`
promised ETAPA 4 would use — swapping the seed source for PostgreSQL touches
neither that file nor this one.

Nothing here imports SQLAlchemy, prompts, styles, shots or providers.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .contracts import (
    PERSONA_IDENTITY_FIELDS,
    PersonaMemory,
    PersonaStatus,
)
from .memory_resolver import SEED_PERSONAS, MemoryError_, MemoryResolver


class PersonaNotFound(MemoryError_):
    """Unknown persona id.

    Subclasses `MemoryError_` so existing `except MemoryError_` handlers keep
    working, while letting the HTTP layer answer 404 instead of 409.
    """

#: Administrative transitions that do not touch identity and therefore do not
#: bump `PersonaMemory.version` — but are still written to the ledger, because
#: an approval is exactly the kind of change an audit trail must show.
ADMIN_ACTIONS: tuple[str, ...] = ("created", "registered", "approved", "retired")

#: A character is only approvable once *something* about its identity exists.
#: This is what stops a planned character from being silently fabricated into a
#: generable one: approval requires definition, it never supplies it.
IDENTITY_DEFINITION_FIELDS: tuple[str, ...] = ("age", "height_m", "body_type", "hair", "beard", "eyes")

Clock = Callable[[], str]


def utc_now() -> str:
    """Deterministic-friendly timestamp. Inject a fixed `clock` in tests."""

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class PersonaVersion:
    """One immutable entry in a character's history."""

    persona_id: str
    revision: int
    version: int
    persona: PersonaMemory
    action: str
    actor: str
    reason: str
    changed: tuple[str, ...]
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "persona_id": self.persona_id,
            "revision": self.revision,
            "version": self.version,
            "action": self.action,
            "actor": self.actor,
            "reason": self.reason,
            "changed": list(self.changed),
            "created_at": self.created_at,
            "persona": self.persona.to_dict(),
        }


class PersonaLedger:
    """Append-only history of persona identities.

    Satisfies `PersonaSource`, so it drops straight into `MemoryResolver` and
    `GenerationSpecBuilder` without either of them knowing that history exists.
    `fetch()` returns the *latest* revision, which keeps every existing caller's
    behaviour identical.
    """

    def __init__(self, personas: tuple[PersonaMemory, ...] = SEED_PERSONAS, clock: Clock = utc_now) -> None:
        self._clock = clock
        self._history: dict[str, list[PersonaVersion]] = {}
        for persona in personas:
            self.register(persona, actor="system", reason="canonical seed")

    # ------------------------------------------------------------------ writes

    def register(self, persona: PersonaMemory, *, actor: str = "system", reason: str = "registered") -> PersonaVersion:
        """Seed or replace a character, starting a fresh history."""

        return self._append(persona, action="registered", actor=actor, reason=reason, changed=())

    def append(
        self,
        persona: PersonaMemory,
        *,
        action: str,
        actor: str,
        reason: str,
        changed: tuple[str, ...] = (),
    ) -> PersonaVersion:
        """Record a new identity state. Nothing is ever overwritten in place."""

        return self._append(persona, action=action, actor=actor, reason=reason, changed=changed)

    def _append(
        self,
        persona: PersonaMemory,
        *,
        action: str,
        actor: str,
        reason: str,
        changed: tuple[str, ...],
    ) -> PersonaVersion:
        history = self._history.setdefault(persona.persona_id, [])
        entry = PersonaVersion(
            persona_id=persona.persona_id,
            revision=len(history) + 1,
            version=persona.version,
            persona=persona,
            action=action,
            actor=actor,
            reason=reason,
            changed=tuple(changed),
            created_at=self._clock(),
        )
        history.append(entry)
        return entry

    # ------------------------------------------------------------------- reads

    def fetch(self, persona_id: str) -> PersonaMemory | None:
        """Latest identity — the `PersonaSource` contract."""

        history = self._history.get(persona_id)
        return history[-1].persona if history else None

    def fetch_revision(self, persona_id: str, revision: int) -> PersonaMemory | None:
        history = self._history.get(persona_id) or []
        for entry in history:
            if entry.revision == revision:
                return entry.persona
        return None

    def fetch_version(self, persona_id: str, version: int) -> PersonaMemory | None:
        """Identity as it stood at a given *identity version*.

        Several ledger revisions can share one identity version (administrative
        transitions do not bump it), so this returns the last revision carrying
        that version — i.e. the state the character actually presented.
        """

        history = self._history.get(persona_id) or []
        for entry in reversed(history):
            if entry.version == version:
                return entry.persona
        return None

    def history(self, persona_id: str) -> tuple[PersonaVersion, ...]:
        return tuple(self._history.get(persona_id) or ())

    def search(self, query: str = "") -> list[PersonaMemory]:
        """Current identities, optionally filtered — the `PersonaSource` contract."""

        current = [persona for persona in (entry.persona for entry in (history[-1] for history in self._history.values()))]
        if not query:
            return current
        needle = query.strip().casefold()
        return [
            persona
            for persona in current
            if needle in persona.persona_id.casefold() or needle in persona.name.casefold()
        ]


class PersonaMemoryEngine:
    """Governed access to persona memory.

    The engine owns *writes* and *history*; `MemoryResolver` owns *vocabulary*
    and the identity-change rule. Neither duplicates the other.
    """

    def __init__(self, ledger: PersonaLedger | None = None, memory: MemoryResolver | None = None) -> None:
        self.ledger = ledger or PersonaLedger()
        # The engine's ledger is the resolver's source, so a persona approved
        # here is immediately visible to GenerationSpecBuilder.
        self.memory = memory or MemoryResolver(self.ledger)
        #: (episode_id, persona_id) -> the identity that episode was made with.
        #: `PersonaMemory` is frozen, so holding the object is safe.
        self._episodes: dict[tuple[str, str], PersonaMemory] = {}

    # ------------------------------------------------------------------ lookup

    def resolve(self, persona_id: str | None, *, version: int | None = None) -> PersonaMemory | None:
        """Current identity, or the identity as of a specific identity version."""

        if not persona_id:
            return None
        if version is None:
            return self.ledger.fetch(persona_id)
        return self.ledger.fetch_version(persona_id, version)

    def catalog(self, query: str = "") -> list[PersonaMemory]:
        return self.ledger.search(query)

    def history(self, persona_id: str) -> tuple[PersonaVersion, ...]:
        return self.ledger.history(persona_id)

    def is_generable(self, persona_id: str | None) -> bool:
        return self.memory.is_generable(persona_id)

    # ------------------------------------------------------- delegated vocabulary
    # Composition, not reimplementation: these are the ETAPA 2 definitions.

    def identity_phrase(self, persona_id: str | None, *, version: int | None = None) -> str:
        return self.memory.identity_phrase(self.resolve(persona_id, version=version))

    def voice_phrase(self, persona_id: str | None, *, version: int | None = None) -> str:
        return self.memory.voice_phrase(self.resolve(persona_id, version=version))

    def default_style(self, persona_id: str | None, *, version: int | None = None) -> str:
        return self.memory.default_style(self.resolve(persona_id, version=version))

    def lora_path(self, persona_id: str | None, *, version: int | None = None) -> str | None:
        return self.memory.lora_path(self.resolve(persona_id, version=version))

    # -------------------------------------------------------------- governance

    def create(
        self,
        *,
        persona_id: str,
        name: str,
        actor: str,
        reason: str = "created",
        authorized: bool = False,
        **attributes: object,
    ) -> PersonaVersion:
        """Register a new character.

        A new character is **planned** until explicitly approved, so registering
        one can never silently make an undefined identity generable.
        """

        if self.ledger.fetch(persona_id) is not None:
            raise MemoryError_(f"persona already exists: {persona_id}")
        status = PersonaStatus.APPROVED if authorized else PersonaStatus.PLANNED
        persona = PersonaMemory(persona_id=persona_id, name=name, status=status, **attributes)  # type: ignore[arg-type]
        return self.ledger.append(persona, action="created", actor=actor, reason=reason)

    def revise(
        self,
        persona_id: str,
        *,
        actor: str,
        reason: str,
        authorized: bool = False,
        **changes: object,
    ) -> PersonaVersion:
        """Edit a character and record it.

        Delegates the *rule* to `MemoryResolver.revise` — identity changes
        without authorisation are rejected there, and only they bump the
        identity version. The engine adds the part that was missing: the change
        is written to the ledger with an actor and a reason.
        """

        current = self._require(persona_id)
        revised = self.memory.revise(current, authorized=authorized, **changes)
        changed = tuple(sorted(name for name in changes if getattr(current, name, None) != getattr(revised, name, None)))
        if not changed:
            raise MemoryError_(f"revision of {persona_id} changes nothing")
        action = "revised" if revised.version != current.version else "updated"
        return self.ledger.append(revised, action=action, actor=actor, reason=reason, changed=changed)

    def approve(self, persona_id: str, *, actor: str, reason: str = "identity approved") -> PersonaVersion:
        """Promote a planned character to approved.

        Refuses when no identity attribute is defined: approval certifies an
        identity, it does not invent one. A planned character stays planned
        until someone actually defines it.
        """

        persona = self._require(persona_id)
        if persona.status is PersonaStatus.APPROVED:
            raise MemoryError_(f"{persona_id} is already approved")
        if not _is_defined(persona):
            raise MemoryError_(
                f"{persona_id} has no defined identity; approval requires definition, it never supplies it"
            )
        revised = self.memory.revise(persona, authorized=True, status=PersonaStatus.APPROVED)
        return self.ledger.append(revised, action="approved", actor=actor, reason=reason)

    def retire(self, persona_id: str, *, actor: str, reason: str) -> PersonaVersion:
        """Retire a character. Existing episodes keep their snapshots."""

        persona = self._require(persona_id)
        if persona.status is PersonaStatus.RETIRED:
            raise MemoryError_(f"{persona_id} is already retired")
        revised = self.memory.revise(persona, authorized=True, status=PersonaStatus.RETIRED)
        return self.ledger.append(revised, action="retired", actor=actor, reason=reason)

    def _require(self, persona_id: str) -> PersonaMemory:
        persona = self.ledger.fetch(persona_id)
        if persona is None:
            raise PersonaNotFound(persona_id)
        return persona

    # ------------------------------------------------------- episode continuity

    def remember(self, persona_id: str, *, episode_id: str, actor: str = "system") -> dict[str, object]:
        """Bind the current identity to an episode.

        This is what makes *"existing episodes keep their original memory
        snapshot"* true rather than aspirational: the snapshot is stored under
        `(episode_id, persona_id)` and is unaffected by later revisions.
        """

        persona = self._require(persona_id)
        self._episodes[(episode_id, persona_id)] = persona
        return self.memory.snapshot(persona)

    def recall(self, episode_id: str, persona_id: str) -> PersonaMemory | None:
        """The identity an episode was actually made with."""

        return self._episodes.get((episode_id, persona_id))

    def episode_cast(self, episode_id: str) -> list[PersonaMemory]:
        return [persona for (episode, _), persona in self._episodes.items() if episode == episode_id]

    def continuity(self, persona_id: str, episodes: list[str]) -> dict[str, object]:
        """Report whether a character stayed consistent across episodes.

        Episodes with no snapshot are listed rather than guessed at — a missing
        record is not the same as a consistent one.
        """

        phrases: dict[str, str] = {}
        missing: list[str] = []
        for episode_id in episodes:
            persona = self.recall(episode_id, persona_id)
            if persona is None:
                missing.append(episode_id)
                continue
            phrases[episode_id] = self.memory.identity_phrase(persona)
        distinct = sorted(set(phrases.values()))
        return {
            "persona_id": persona_id,
            "episodes": list(episodes),
            "consistent": len(distinct) <= 1 and not missing,
            "identity_phrases": phrases,
            "distinct_identities": len(distinct),
            "episodes_without_snapshot": missing,
        }

    # ------------------------------------------------------------------- drift

    def drift(self, persona_id: str) -> dict[str, object]:
        """Which **identity** fields changed across the character's versions.

        Answers "what is different about this character now?" without anyone
        having to remember, which is the point of keeping the ledger.
        Administrative edits (LoRA path, default style, status) are deliberately
        excluded: they are churn, not identity drift, and they remain visible in
        `history` either way.
        """

        history = self.ledger.history(persona_id)
        changed: dict[str, list[int]] = {}
        for entry in history:
            for field_name in entry.changed:
                if field_name not in PERSONA_IDENTITY_FIELDS:
                    continue
                changed.setdefault(field_name, []).append(entry.version)
        return {
            "persona_id": persona_id,
            "revisions": len(history),
            "identity_versions": sorted({entry.version for entry in history}),
            "changed_fields": {name: sorted(set(versions)) for name, versions in sorted(changed.items())},
            "identity_changed": any(entry.version > 1 for entry in history),
        }


def _is_defined(persona: PersonaMemory) -> bool:
    return any(getattr(persona, name) for name in IDENTITY_DEFINITION_FIELDS)
