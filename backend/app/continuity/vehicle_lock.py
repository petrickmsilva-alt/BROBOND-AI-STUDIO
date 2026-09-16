"""V3.2 — Vehicle Lock: the frozen hero vehicle of a campaign.

Persists vehicle, color, optional plate, wheels and finish per
(persona, campaign) with an optional per-episode override. The plate is
explicitly optional — everything else identifies the car on screen — while
the vehicle model and its color are mandatory.

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


#: The five frozen vehicle fields, in fingerprint order.
VEHICLE_FIELDS: tuple[str, ...] = (
    "vehicle",
    "color",
    "plate",
    "wheels",
    "finish",
)


@dataclass(frozen=True)
class VehicleSnapshot:
    """A campaign's frozen hero vehicle, plus its fingerprint."""

    vehicle: str = ""
    color: str = ""
    plate: str = ""
    wheels: str = ""
    finish: str = ""
    fingerprint: str = ""

    def fields(self) -> tuple[str, ...]:
        """The five frozen fields, in fingerprint order."""

        return (self.vehicle, self.color, self.plate, self.wheels, self.finish)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class VehicleLock:
    """Freezes the hero vehicle, fingerprints it and phrases it for direction."""

    @staticmethod
    def lock(
        *,
        vehicle: str = "",
        color: str = "",
        plate: str = "",
        wheels: str = "",
        finish: str = "",
    ) -> VehicleSnapshot:
        """Freeze a vehicle. Model and color are mandatory; plate is optional."""

        cleaned = {
            name: clean_field(value, name)
            for name, value in (
                ("vehicle", vehicle),
                ("color", color),
                ("plate", plate),
                ("wheels", wheels),
                ("finish", finish),
            )
        }
        if not cleaned["vehicle"]:
            raise ContinuityValidationError("vehicle lock requires a vehicle")
        if not cleaned["color"]:
            raise ContinuityValidationError("vehicle lock requires a color")
        ordered = tuple(cleaned[name] for name in VEHICLE_FIELDS)
        return VehicleSnapshot(
            vehicle=cleaned["vehicle"],
            color=cleaned["color"],
            plate=cleaned["plate"],
            wheels=cleaned["wheels"],
            finish=cleaned["finish"],
            fingerprint=fingerprint_for(ordered),
        )

    @staticmethod
    def fingerprint_of(snapshot: VehicleSnapshot) -> str:
        """Recompute the fingerprint from a snapshot's fields."""

        return fingerprint_for(snapshot.fields())

    @staticmethod
    def verify(snapshot: VehicleSnapshot, **candidate: str) -> bool:
        """Return whether candidate fields reproduce the locked fingerprint."""

        ordered = tuple(clean_field(candidate.get(name, ""), name) for name in VEHICLE_FIELDS)
        return hmac.compare_digest(fingerprint_for(ordered), snapshot.fingerprint)

    @staticmethod
    def phrase(snapshot: VehicleSnapshot) -> str:
        """One cinematic continuity phrase, with only the defined parts."""

        labels = (
            ("veículo", snapshot.vehicle),
            ("cor", snapshot.color),
            ("placa", snapshot.plate),
            ("rodas", snapshot.wheels),
            ("acabamento", snapshot.finish),
        )
        parts = [f"{label} {value}" for label, value in labels if value]
        if not parts:
            return "veículo travado"
        return "veículo travado: " + "; ".join(parts)

    @staticmethod
    def from_dict(payload: Mapping[str, object], *, fingerprint: str = "") -> VehicleSnapshot:
        """Rebuild a snapshot from a persisted payload (see IdentityLock)."""

        if not isinstance(payload, Mapping):
            raise ContinuityValidationError("vehicle payload must be an object")
        cleaned = {name: clean_field(payload.get(name, ""), name) for name in VEHICLE_FIELDS}
        return VehicleSnapshot(
            vehicle=cleaned["vehicle"],
            color=cleaned["color"],
            plate=cleaned["plate"],
            wheels=cleaned["wheels"],
            finish=cleaned["finish"],
            fingerprint=fingerprint.strip() if isinstance(fingerprint, str) else "",
        )
