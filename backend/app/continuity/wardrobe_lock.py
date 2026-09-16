"""V3.2 — Wardrobe Lock: the frozen costume of a character.

Persists outfit, accessories, colors, shoes and watch per
(persona, campaign) with an optional per-episode override: the campaign
default dresses every episode unless that episode carries its own wardrobe.
Changing episodes never rewrites history — each episode keeps the wardrobe
it was locked with.

Framework-free: the shared error and fingerprint come from
``identity_lock`` (the package kernel); persistence lives in
``continuity_repository.py``.
"""
from __future__ import annotations

import hmac
from dataclasses import asdict, dataclass
from typing import Mapping

from .identity_lock import (
    ContinuityValidationError,
    clean_field,
    fingerprint_for,
)


#: The five frozen wardrobe fields, in fingerprint order.
WARDROBE_FIELDS: tuple[str, ...] = (
    "outfit",
    "accessories",
    "colors",
    "shoes",
    "watch",
)


@dataclass(frozen=True)
class WardrobeSnapshot:
    """A character's frozen costume, plus its fingerprint."""

    outfit: str = ""
    accessories: str = ""
    colors: str = ""
    shoes: str = ""
    watch: str = ""
    fingerprint: str = ""

    def fields(self) -> tuple[str, ...]:
        """The five frozen fields, in fingerprint order."""

        return (self.outfit, self.accessories, self.colors, self.shoes, self.watch)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class WardrobeLock:
    """Freezes costume, fingerprints it and phrases it for direction."""

    @staticmethod
    def lock(
        *,
        outfit: str = "",
        accessories: str = "",
        colors: str = "",
        shoes: str = "",
        watch: str = "",
    ) -> WardrobeSnapshot:
        """Freeze a costume. The outfit itself is mandatory.

        Accessories, colors, shoes and watch refine the look; an empty
        outfit is not a look, so it is refused.
        """

        cleaned = {
            name: clean_field(value, name)
            for name, value in (
                ("outfit", outfit),
                ("accessories", accessories),
                ("colors", colors),
                ("shoes", shoes),
                ("watch", watch),
            )
        }
        if not cleaned["outfit"]:
            raise ContinuityValidationError("wardrobe lock requires an outfit")
        ordered = tuple(cleaned[name] for name in WARDROBE_FIELDS)
        return WardrobeSnapshot(
            outfit=cleaned["outfit"],
            accessories=cleaned["accessories"],
            colors=cleaned["colors"],
            shoes=cleaned["shoes"],
            watch=cleaned["watch"],
            fingerprint=fingerprint_for(ordered),
        )

    @staticmethod
    def fingerprint_of(snapshot: WardrobeSnapshot) -> str:
        """Recompute the fingerprint from a snapshot's fields."""

        return fingerprint_for(snapshot.fields())

    @staticmethod
    def verify(snapshot: WardrobeSnapshot, **candidate: str) -> bool:
        """Return whether candidate fields reproduce the locked fingerprint."""

        ordered = tuple(clean_field(candidate.get(name, ""), name) for name in WARDROBE_FIELDS)
        return hmac.compare_digest(fingerprint_for(ordered), snapshot.fingerprint)

    @staticmethod
    def phrase(snapshot: WardrobeSnapshot) -> str:
        """One cinematic continuity phrase, with only the defined parts."""

        labels = (
            ("figurino", snapshot.outfit),
            ("acessórios", snapshot.accessories),
            ("cores", snapshot.colors),
            ("calçados", snapshot.shoes),
            ("relógio", snapshot.watch),
        )
        parts = [f"{label} {value}" for label, value in labels if value]
        if not parts:
            return "figurino travado"
        return "figurino travado: " + "; ".join(parts)

    @staticmethod
    def from_dict(payload: Mapping[str, object], *, fingerprint: str = "") -> WardrobeSnapshot:
        """Rebuild a snapshot from a persisted payload (see IdentityLock)."""

        if not isinstance(payload, Mapping):
            raise ContinuityValidationError("wardrobe payload must be an object")
        cleaned = {name: clean_field(payload.get(name, ""), name) for name in WARDROBE_FIELDS}
        return WardrobeSnapshot(
            outfit=cleaned["outfit"],
            accessories=cleaned["accessories"],
            colors=cleaned["colors"],
            shoes=cleaned["shoes"],
            watch=cleaned["watch"],
            fingerprint=fingerprint.strip() if isinstance(fingerprint, str) else "",
        )
