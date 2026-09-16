"""ShotPlan — immutable planning contract for one storyboard scene."""
from __future__ import annotations

from dataclasses import asdict, dataclass

FIRST_SCENE_NUMBER = 1
ZERO_SECONDS = 0.0

_TEXT_FIELDS: tuple[str, ...] = (
    "title",
    "objective",
    "emotion",
    "camera",
    "lens",
    "lighting",
    "motion",
    "prompt",
    "negative_prompt",
    "environment",
)


@dataclass(frozen=True)
class ShotPlan:
    """A single required scene in a production plan.

    It is planning data only: no provider id, no job id and no rendered asset.
    """

    scene_number: int
    title: str
    objective: str
    emotion: str
    camera: str
    lens: str
    lighting: str
    motion: str
    duration: float
    prompt: str
    negative_prompt: str
    environment: str

    def __post_init__(self) -> None:
        if self.scene_number < FIRST_SCENE_NUMBER:
            raise ValueError("scene_number must be positive")
        if self.duration <= ZERO_SECONDS:
            raise ValueError("duration must be positive")
        for field_name in _TEXT_FIELDS:
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} is required")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
