"""V3.2 — Continuity Resolver: one cinematic context per episode.

``ContinuityResolver.resolve(persona_id, campaign_id, episode)`` answers
"what is locked for this character, in this campaign, in this episode?" and
returns a ``ContinuityContext``: the five typed snapshots (or ``None`` where
nothing is locked), the cinematic phrases, the stored fingerprints, what is
missing, what drifted and whether the context is consistent.

The resolver never touches ``GenerationSpec``. It produces context that
callers consume explicitly — the ``continuity`` block of a compiled prompt,
an episode snapshot, the studio UI — the same enrichment-only rule V3.1 set
for the Knowledge Graph: the Director, the Provider Registry and the Render
Engine are not altered.

Framework-free: the store is injected through the ``ContinuityStore``
protocol (the repository binds it to one workspace), and every lock type is
read through its own ``from_dict``/``phrase``/``fingerprint_of`` — the
resolver owns no lock vocabulary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, runtime_checkable

from .identity_lock import (
    ContinuityValidationError,
    IdentityLock,
    IdentitySnapshot,
    normalize_campaign,
    normalize_episode,
    normalize_persona_id,
)
from .location_lock import LocationLock, LocationSnapshot
from .vehicle_lock import VehicleLock, VehicleSnapshot
from .voice_lock import VoiceLock, VoiceSnapshot
from .wardrobe_lock import WardrobeLock, WardrobeSnapshot


@runtime_checkable
class StoredLock(Protocol):
    """What the resolver needs from a persisted lock (structural)."""

    @property
    def payload(self) -> Mapping[str, object]:
        """The persisted attribute payload."""

    @property
    def fingerprint(self) -> str:
        """The fingerprint stored beside the payload."""


@runtime_checkable
class ContinuityStore(Protocol):
    """Where locked continuity is read from (repository adapter)."""

    def get_lock(
        self,
        lock_type: str,
        persona_id: str,
        campaign_id: str,
        episode: int | None,
    ) -> StoredLock | None:
        """Return the most specific lock, or None when nothing is locked."""


#: Lock resolution order: identity first, voice last. Phrase order is fixed
#: so the continuity block reads the same in every episode.
LOCK_ORDER: tuple[str, ...] = ("identity", "wardrobe", "location", "vehicle", "voice")


@dataclass(frozen=True)
class ContinuityContext:
    """Everything locked for one (persona, campaign, episode)."""

    persona_id: str
    campaign_id: str
    episode: int
    identity: IdentitySnapshot | None = None
    wardrobe: WardrobeSnapshot | None = None
    location: LocationSnapshot | None = None
    vehicle: VehicleSnapshot | None = None
    voice: VoiceSnapshot | None = None
    phrases: tuple[str, ...] = ()
    fingerprints: tuple[tuple[str, str], ...] = ()
    missing: tuple[str, ...] = ()
    #: Locks whose stored fingerprint no longer matches their payload —
    #: the row was edited outside a lock write.
    drift: tuple[str, ...] = ()
    consistent: bool = False

    def block(self) -> str:
        """The cinematic continuity block: phrases joined, or blank."""

        return " ".join(self.phrases)

    def fingerprint_map(self) -> dict[str, str]:
        """Stored fingerprints by lock type."""

        return dict(self.fingerprints)

    def to_dict(self) -> dict[str, object]:
        return {
            "persona_id": self.persona_id,
            "campaign_id": self.campaign_id,
            "episode": self.episode,
            "identity": self.identity.to_dict() if self.identity else None,
            "wardrobe": self.wardrobe.to_dict() if self.wardrobe else None,
            "location": self.location.to_dict() if self.location else None,
            "vehicle": self.vehicle.to_dict() if self.vehicle else None,
            "voice": self.voice.to_dict() if self.voice else None,
            "phrases": list(self.phrases),
            "fingerprints": self.fingerprint_map(),
            "missing": list(self.missing),
            "drift": list(self.drift),
            "consistent": self.consistent,
            "block": self.block(),
        }


class ContinuityResolver:
    """Resolves the five locks into one context. Enrichment only."""

    def __init__(self, store: ContinuityStore | None = None) -> None:
        self._store = store

    def resolve(
        self,
        persona_id: str,
        campaign_id: str | None = "default",
        episode: int | None = 1,
    ) -> ContinuityContext:
        """Return the continuity context for one episode.

        With no store every lock is missing — a valid empty context, never
        an error. A blank persona id or an invalid episode is refused: the
        resolver needs an anchor to resolve against.
        """

        cleaned_persona = normalize_persona_id(persona_id)
        cleaned_campaign = normalize_campaign(campaign_id if campaign_id is not None else "default")
        cleaned_episode = normalize_episode(1 if episode is None else episode)
        assert cleaned_episode is not None  # normalize_episode(>=1) never returns None

        snapshots: dict[str, object] = {}
        phrases: list[str] = []
        fingerprints: list[tuple[str, str]] = []
        missing: list[str] = []
        drift: list[str] = []
        for lock_type in LOCK_ORDER:
            stored = self._store.get_lock(lock_type, cleaned_persona, cleaned_campaign, cleaned_episode) if self._store else None
            if stored is None:
                missing.append(lock_type)
                continue
            snapshot = _rebuild(lock_type, cleaned_persona, stored)
            snapshots[lock_type] = snapshot
            fingerprints.append((lock_type, stored.fingerprint))
            if _recomputed(lock_type, snapshot) != stored.fingerprint:
                drift.append(lock_type)
            phrases.append(_phrase(lock_type, snapshot))

        return ContinuityContext(
            persona_id=cleaned_persona,
            campaign_id=cleaned_campaign,
            episode=cleaned_episode,
            identity=snapshots.get("identity"),  # type: ignore[arg-type]
            wardrobe=snapshots.get("wardrobe"),  # type: ignore[arg-type]
            location=snapshots.get("location"),  # type: ignore[arg-type]
            vehicle=snapshots.get("vehicle"),  # type: ignore[arg-type]
            voice=snapshots.get("voice"),  # type: ignore[arg-type]
            phrases=tuple(phrases),
            fingerprints=tuple(fingerprints),
            missing=tuple(missing),
            drift=tuple(drift),
            consistent=not missing and not drift,
        )

    def snapshot_dict(self, context: ContinuityContext) -> dict[str, object]:
        """Return the JSON-able snapshot an episode freezes.

        Episodes store this verbatim: fingerprints to compare across
        episodes, phrases for direction, and the lock payloads behind them.
        """

        locks: dict[str, object] = {}
        for lock_type in LOCK_ORDER:
            snapshot = getattr(context, lock_type)
            if snapshot is not None:
                locks[lock_type] = snapshot.to_dict()
        return {
            "persona_id": context.persona_id,
            "campaign_id": context.campaign_id,
            "episode": context.episode,
            "fingerprints": context.fingerprint_map(),
            "phrases": list(context.phrases),
            "locks": locks,
            "missing": list(context.missing),
            "drift": list(context.drift),
            "consistent": context.consistent,
        }


def _rebuild(lock_type: str, persona_id: str, stored: StoredLock):
    """Rebuild a typed snapshot from a stored lock (unknown types refused)."""

    payload = stored.payload
    fingerprint = stored.fingerprint
    if lock_type == "identity":
        snapshot = IdentityLock.from_dict(payload, fingerprint=fingerprint)
        if not snapshot.persona_id:
            return IdentitySnapshot(
                persona_id=persona_id,
                face=snapshot.face,
                hair=snapshot.hair,
                beard=snapshot.beard,
                body=snapshot.body,
                skin=snapshot.skin,
                age_appearance=snapshot.age_appearance,
                fingerprint=snapshot.fingerprint,
            )
        return snapshot
    if lock_type == "wardrobe":
        return WardrobeLock.from_dict(payload, fingerprint=fingerprint)
    if lock_type == "location":
        return LocationLock.from_dict(payload, fingerprint=fingerprint)
    if lock_type == "vehicle":
        return VehicleLock.from_dict(payload, fingerprint=fingerprint)
    if lock_type == "voice":
        return VoiceLock.from_dict(payload, fingerprint=fingerprint)
    raise ContinuityValidationError(f"unknown lock type: {lock_type!r}")


def _recomputed(lock_type: str, snapshot) -> str:
    if lock_type == "identity":
        return IdentityLock.fingerprint_of(snapshot)
    if lock_type == "wardrobe":
        return WardrobeLock.fingerprint_of(snapshot)
    if lock_type == "location":
        return LocationLock.fingerprint_of(snapshot)
    if lock_type == "vehicle":
        return VehicleLock.fingerprint_of(snapshot)
    return VoiceLock.fingerprint_of(snapshot)


def _phrase(lock_type: str, snapshot) -> str:
    if lock_type == "identity":
        return IdentityLock.phrase(snapshot)
    if lock_type == "wardrobe":
        return WardrobeLock.phrase(snapshot)
    if lock_type == "location":
        return LocationLock.phrase(snapshot)
    if lock_type == "vehicle":
        return VehicleLock.phrase(snapshot)
    return VoiceLock.phrase(snapshot)
