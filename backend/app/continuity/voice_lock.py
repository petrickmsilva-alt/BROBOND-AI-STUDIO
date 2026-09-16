"""V3.2 — Voice Lock: the frozen voice of a character.

Persists the voice profile, default emotion, speed and intensity per
persona (persona-global, like the Identity Lock — a character sounds the
same in every campaign until a new voice is explicitly locked). The voice
profile is mandatory; emotion, speed and intensity refine the delivery.

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


#: The four frozen voice fields, in fingerprint order.
VOICE_FIELDS: tuple[str, ...] = (
    "voice_profile",
    "default_emotion",
    "speed",
    "intensity",
)


@dataclass(frozen=True)
class VoiceSnapshot:
    """A character's frozen voice, plus its fingerprint."""

    voice_profile: str = ""
    default_emotion: str = ""
    speed: str = ""
    intensity: str = ""
    fingerprint: str = ""

    def fields(self) -> tuple[str, ...]:
        """The four frozen fields, in fingerprint order."""

        return (self.voice_profile, self.default_emotion, self.speed, self.intensity)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class VoiceLock:
    """Freezes the voice, fingerprints it and phrases it for direction."""

    @staticmethod
    def lock(
        *,
        voice_profile: str = "",
        default_emotion: str = "",
        speed: str = "",
        intensity: str = "",
    ) -> VoiceSnapshot:
        """Freeze a voice. The voice profile itself is mandatory."""

        cleaned = {
            name: clean_field(value, name)
            for name, value in (
                ("voice_profile", voice_profile),
                ("default_emotion", default_emotion),
                ("speed", speed),
                ("intensity", intensity),
            )
        }
        if not cleaned["voice_profile"]:
            raise ContinuityValidationError("voice lock requires a voice profile")
        ordered = tuple(cleaned[name] for name in VOICE_FIELDS)
        return VoiceSnapshot(
            voice_profile=cleaned["voice_profile"],
            default_emotion=cleaned["default_emotion"],
            speed=cleaned["speed"],
            intensity=cleaned["intensity"],
            fingerprint=fingerprint_for(ordered),
        )

    @staticmethod
    def fingerprint_of(snapshot: VoiceSnapshot) -> str:
        """Recompute the fingerprint from a snapshot's fields."""

        return fingerprint_for(snapshot.fields())

    @staticmethod
    def verify(snapshot: VoiceSnapshot, **candidate: str) -> bool:
        """Return whether candidate fields reproduce the locked fingerprint."""

        ordered = tuple(clean_field(candidate.get(name, ""), name) for name in VOICE_FIELDS)
        return hmac.compare_digest(fingerprint_for(ordered), snapshot.fingerprint)

    @staticmethod
    def phrase(snapshot: VoiceSnapshot) -> str:
        """One cinematic continuity phrase, with only the defined parts."""

        labels = (
            ("perfil de voz", snapshot.voice_profile),
            ("emoção", snapshot.default_emotion),
            ("velocidade", snapshot.speed),
            ("intensidade", snapshot.intensity),
        )
        parts = [f"{label} {value}" for label, value in labels if value]
        if not parts:
            return "voz travada"
        return "voz travada: " + "; ".join(parts)

    @staticmethod
    def from_dict(payload: Mapping[str, object], *, fingerprint: str = "") -> VoiceSnapshot:
        """Rebuild a snapshot from a persisted payload (see IdentityLock)."""

        if not isinstance(payload, Mapping):
            raise ContinuityValidationError("voice payload must be an object")
        cleaned = {name: clean_field(payload.get(name, ""), name) for name in VOICE_FIELDS}
        return VoiceSnapshot(
            voice_profile=cleaned["voice_profile"],
            default_emotion=cleaned["default_emotion"],
            speed=cleaned["speed"],
            intensity=cleaned["intensity"],
            fingerprint=fingerprint.strip() if isinstance(fingerprint, str) else "",
        )
