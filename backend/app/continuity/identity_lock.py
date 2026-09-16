"""V3.2 — Identity Lock: the frozen visual identity of a character.

The Identity Lock freezes what a character looks like — face, hair, beard,
body, skin and age appearance — and derives a deterministic visual
fingerprint from those fields, so any scene, episode or campaign can answer
"is this still the same person?" by comparing sixteen hex characters.

This module is also the home of the package kernel that every other lock
imports, so the package has exactly one definition of each:

* ``ContinuityValidationError`` — the single validation error (routes map it
  to 422, like ``GraphValidationError`` in V3.1);
* ``fingerprint_for`` — the canonical fingerprint algorithm;
* ``normalize_persona_id`` / ``normalize_campaign`` / ``normalize_episode`` —
  the key normalisation every lock and the resolver share.

Framework-free: standard library only. Persistence lives in
``continuity_repository.py``; the resolver lives in
``continuity_resolver.py``. Neither is imported here, so there are no cycles.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import asdict, dataclass
from typing import Mapping


class ContinuityValidationError(ValueError):
    """Raised when continuity input violates the domain vocabulary."""


def fingerprint_for(parts: tuple[str, ...]) -> str:
    """Return the canonical 16-hex fingerprint for normalised fields.

    Case and surrounding whitespace do not move the fingerprint — "Barba
    curta" and "barba curta " lock the same identity — while any other
    change does. The unit separator keeps ("ab", "c") distinct from
    ("a", "bc").
    """

    canonical = "\x1f".join(part.strip().casefold() for part in parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def normalize_persona_id(value: object) -> str:
    """Return the stripped persona id, or raise when blank/not a string."""

    if not isinstance(value, str) or not value.strip():
        raise ContinuityValidationError("persona_id must not be blank")
    return value.strip()


def normalize_campaign(value: object) -> str:
    """Return the stripped campaign id, defaulting blanks to "default"."""

    if value is None:
        return "default"
    if not isinstance(value, str):
        raise ContinuityValidationError("campaign_id must be a string")
    return value.strip() or "default"


def normalize_episode(value: object) -> int | None:
    """Return the episode scope: None (campaign default) or an int >= 1.

    ``None`` means the lock is the campaign default that every episode
    inherits unless it carries its own override. Booleans are rejected
    explicitly — ``True`` is an ``int`` in Python but never an episode.
    """

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContinuityValidationError("episode must be an int >= 1 or null (campaign default)")
    if value < 1:
        raise ContinuityValidationError("episode must be an int >= 1 or null (campaign default)")
    return value


def clean_field(value: object, field_name: str) -> str:
    """Return the stripped string value, or raise when it is not a string."""

    if not isinstance(value, str):
        raise ContinuityValidationError(f"{field_name} must be a string")
    return value.strip()


_clean = clean_field


#: The six frozen identity fields, in fingerprint order.
IDENTITY_FIELDS: tuple[str, ...] = (
    "face",
    "hair",
    "beard",
    "body",
    "skin",
    "age_appearance",
)


@dataclass(frozen=True)
class IdentitySnapshot:
    """A character's frozen visual identity, plus its fingerprint."""

    persona_id: str
    face: str = ""
    hair: str = ""
    beard: str = ""
    body: str = ""
    skin: str = ""
    age_appearance: str = ""
    fingerprint: str = ""

    def fields(self) -> tuple[str, ...]:
        """The six frozen fields, in fingerprint order."""

        return (self.face, self.hair, self.beard, self.body, self.skin, self.age_appearance)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class IdentityLock:
    """Freezes identity, fingerprints it and phrases it for direction."""

    @staticmethod
    def lock(
        persona_id: str,
        *,
        face: str = "",
        hair: str = "",
        beard: str = "",
        body: str = "",
        skin: str = "",
        age_appearance: str = "",
    ) -> IdentitySnapshot:
        """Freeze an identity. At least one attribute must be defined.

        Mirrors the PersonaMemoryEngine approval rule: a lock certifies an
        identity, it never invents one — locking six blank fields is refused.
        """

        cleaned_id = normalize_persona_id(persona_id)
        cleaned = {
            name: _clean(value, name)
            for name, value in (
                ("face", face),
                ("hair", hair),
                ("beard", beard),
                ("body", body),
                ("skin", skin),
                ("age_appearance", age_appearance),
            )
        }
        if not any(cleaned.values()):
            raise ContinuityValidationError(
                "identity lock requires at least one defined attribute "
                "(face, hair, beard, body, skin, age_appearance)"
            )
        ordered = tuple(cleaned[name] for name in IDENTITY_FIELDS)
        return IdentitySnapshot(
            persona_id=cleaned_id,
            face=cleaned["face"],
            hair=cleaned["hair"],
            beard=cleaned["beard"],
            body=cleaned["body"],
            skin=cleaned["skin"],
            age_appearance=cleaned["age_appearance"],
            fingerprint=fingerprint_for(ordered),
        )

    @staticmethod
    def fingerprint_of(snapshot: IdentitySnapshot) -> str:
        """Recompute the fingerprint from a snapshot's fields."""

        return fingerprint_for(snapshot.fields())

    @staticmethod
    def verify(snapshot: IdentitySnapshot, **candidate: str) -> bool:
        """Return whether candidate fields reproduce the locked fingerprint.

        Unknown keywords are ignored; missing ones default to blank — so a
        partial candidate only verifies when the locked fields it omits are
        themselves blank.
        """

        ordered = tuple(_clean(candidate.get(name, ""), name) for name in IDENTITY_FIELDS)
        return hmac.compare_digest(fingerprint_for(ordered), snapshot.fingerprint)

    @staticmethod
    def phrase(snapshot: IdentitySnapshot) -> str:
        """One cinematic continuity phrase, with only the defined parts."""

        labels = (
            ("rosto", snapshot.face),
            ("cabelo", snapshot.hair),
            ("barba", snapshot.beard),
            ("corpo", snapshot.body),
            ("pele", snapshot.skin),
            ("aparência de", snapshot.age_appearance),
        )
        parts = [f"{label} {value}" for label, value in labels if value]
        if not parts:
            return f"mesmo personagem {snapshot.persona_id}"
        return f"mesmo personagem {snapshot.persona_id}: " + "; ".join(parts)

    @staticmethod
    def from_dict(payload: Mapping[str, object], *, fingerprint: str = "") -> IdentitySnapshot:
        """Rebuild a snapshot from a persisted payload.

        Unknown keys are ignored (forward compatibility); known keys must be
        strings. The fingerprint travels beside the payload in storage, so it
        arrives as an explicit argument rather than being recomputed — the
        resolver compares stored versus recomputed to detect drift.
        """

        if not isinstance(payload, Mapping):
            raise ContinuityValidationError("identity payload must be an object")
        cleaned = {name: _clean(payload.get(name, ""), name) for name in IDENTITY_FIELDS}
        persona_id = payload.get("persona_id", "")
        return IdentitySnapshot(
            persona_id=persona_id.strip() if isinstance(persona_id, str) else "",
            fingerprint=fingerprint.strip() if isinstance(fingerprint, str) else "",
            **cleaned,  # type: ignore[arg-type]
        )
