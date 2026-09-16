"""ProductionPlan — immutable output of the Director AI Engine."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from .shot_plan import ShotPlan

ZERO_SECONDS = 0.0
MINIMUM_PRODUCTION_SHOTS = 1

_REQUIRED_TEXT_FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "concept",
    "mood",
    "audience",
    "platform",
    "style",
    "music",
    "voice",
)


@dataclass(frozen=True)
class ProductionPlan:
    """The central, immutable planning entity produced by PR005."""

    id: str
    title: str
    concept: str
    mood: str
    audience: str
    platform: str
    duration: float
    style: str
    music: str
    voice: str
    persona_id: str | None
    shots: tuple[ShotPlan, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.shots, tuple):
            object.__setattr__(self, "shots", tuple(self.shots))
        if self.duration <= ZERO_SECONDS:
            raise ValueError("duration must be positive")
        if not isinstance(self.created_at, datetime):
            raise ValueError("created_at must be a datetime")
        if len(self.shots) < MINIMUM_PRODUCTION_SHOTS:
            raise ValueError("shots are required")
        for shot in self.shots:
            if not isinstance(shot, ShotPlan):
                raise ValueError("shots must contain ShotPlan instances")
        for field_name in _REQUIRED_TEXT_FIELDS:
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} is required")

    @property
    def scene_count(self) -> int:
        return len(self.shots)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["shots"] = [shot.to_dict() for shot in self.shots]
        payload["created_at"] = self.created_at.isoformat()
        return payload
