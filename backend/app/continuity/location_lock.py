"""V3.2 — Location Lock: the frozen set of a campaign.

Persists showroom, studio, street, city and base lighting per
(persona, campaign) with an optional per-episode override: the campaign
default dresses every episode unless that episode carries its own location.
At least one venue (showroom, studio or street) is mandatory — a lock with
only a city is an address, not a set.

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


#: The five frozen location fields, in fingerprint order.
LOCATION_FIELDS: tuple[str, ...] = (
    "showroom",
    "studio",
    "street",
    "city",
    "base_lighting",
)

#: Venues: at least one must be defined for the lock to be a set.
LOCATION_VENUES: tuple[str, ...] = ("showroom", "studio", "street")


@dataclass(frozen=True)
class LocationSnapshot:
    """A campaign's frozen set, plus its fingerprint."""

    showroom: str = ""
    studio: str = ""
    street: str = ""
    city: str = ""
    base_lighting: str = ""
    fingerprint: str = ""

    def fields(self) -> tuple[str, ...]:
        """The five frozen fields, in fingerprint order."""

        return (self.showroom, self.studio, self.street, self.city, self.base_lighting)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class LocationLock:
    """Freezes the set, fingerprints it and phrases it for direction."""

    @staticmethod
    def lock(
        *,
        showroom: str = "",
        studio: str = "",
        street: str = "",
        city: str = "",
        base_lighting: str = "",
    ) -> LocationSnapshot:
        """Freeze a location. At least one venue must be defined."""

        cleaned = {
            name: clean_field(value, name)
            for name, value in (
                ("showroom", showroom),
                ("studio", studio),
                ("street", street),
                ("city", city),
                ("base_lighting", base_lighting),
            )
        }
        if not any(cleaned[name] for name in LOCATION_VENUES):
            raise ContinuityValidationError(
                "location lock requires at least one venue (showroom, studio, street)"
            )
        ordered = tuple(cleaned[name] for name in LOCATION_FIELDS)
        return LocationSnapshot(
            showroom=cleaned["showroom"],
            studio=cleaned["studio"],
            street=cleaned["street"],
            city=cleaned["city"],
            base_lighting=cleaned["base_lighting"],
            fingerprint=fingerprint_for(ordered),
        )

    @staticmethod
    def fingerprint_of(snapshot: LocationSnapshot) -> str:
        """Recompute the fingerprint from a snapshot's fields."""

        return fingerprint_for(snapshot.fields())

    @staticmethod
    def verify(snapshot: LocationSnapshot, **candidate: str) -> bool:
        """Return whether candidate fields reproduce the locked fingerprint."""

        ordered = tuple(clean_field(candidate.get(name, ""), name) for name in LOCATION_FIELDS)
        return hmac.compare_digest(fingerprint_for(ordered), snapshot.fingerprint)

    @staticmethod
    def phrase(snapshot: LocationSnapshot) -> str:
        """One cinematic continuity phrase, with only the defined parts."""

        labels = (
            ("showroom", snapshot.showroom),
            ("estúdio", snapshot.studio),
            ("rua", snapshot.street),
            ("cidade", snapshot.city),
            ("luz base", snapshot.base_lighting),
        )
        parts = [f"{label} {value}" for label, value in labels if value]
        if not parts:
            return "locação travada"
        return "locação travada: " + "; ".join(parts)

    @staticmethod
    def from_dict(payload: Mapping[str, object], *, fingerprint: str = "") -> LocationSnapshot:
        """Rebuild a snapshot from a persisted payload (see IdentityLock)."""

        if not isinstance(payload, Mapping):
            raise ContinuityValidationError("location payload must be an object")
        cleaned = {name: clean_field(payload.get(name, ""), name) for name in LOCATION_FIELDS}
        return LocationSnapshot(
            showroom=cleaned["showroom"],
            studio=cleaned["studio"],
            street=cleaned["street"],
            city=cleaned["city"],
            base_lighting=cleaned["base_lighting"],
            fingerprint=fingerprint.strip() if isinstance(fingerprint, str) else "",
        )
