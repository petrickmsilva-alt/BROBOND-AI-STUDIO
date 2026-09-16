"""PR006 StoryboardState — versioned cinematic plan editor.

This module edits planning data only. It never imports provider adapters, never
creates jobs and never renders images. Every operation returns a new immutable
StoryboardState with an incremented version and refreshed timeline.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

from .mood_config import MOOD_NAMES, MoodPreset
from .mood_engine import MoodEngine
from .production_plan import ProductionPlan
from .shot_plan import FIRST_SCENE_NUMBER, ShotPlan

INITIAL_STORYBOARD_VERSION = 1
MINIMUM_SCENE_DURATION = 0.1
MINIMUM_EDITOR_SCENES = 1
TIMELINE_PRECISION_DIGITS = 2
STORYBOARD_HISTORY_LIMIT = 50

CAMERA_PRESET_HERO_WALK = "Hero Walk"
CAMERA_PRESET_ORBIT = "Orbit"
CAMERA_PRESET_TRACKING = "Tracking"
CAMERA_PRESET_CRANE = "Crane"
CAMERA_PRESET_DRONE = "Drone"
CAMERA_PRESET_STATIC = "Static"

EDITABLE_SCENE_FIELDS = frozenset(
    {
        "title",
        "objective",
        "emotion",
        "camera",
        "lens",
        "lighting",
        "motion",
        "duration",
        "environment",
    }
)

TEXT_SCENE_FIELDS = frozenset(
    {
        "id",
        "title",
        "objective",
        "emotion",
        "camera",
        "lens",
        "lighting",
        "motion",
        "environment",
        "mood",
        "lut",
        "prompt",
        "negative_prompt",
    }
)


@dataclass(frozen=True)
class CameraPanelPreset:
    """Camera Panel choice that updates only the camera-direction slice."""

    name: str
    camera: str
    lens: str
    lighting: str
    motion: str


CAMERA_PANEL_PRESETS: dict[str, CameraPanelPreset] = {
    CAMERA_PRESET_HERO_WALK: CameraPanelPreset(
        name=CAMERA_PRESET_HERO_WALK,
        camera=CAMERA_PRESET_HERO_WALK,
        lens="35mm anamorphic",
        lighting="motivated hero key with controlled rim light",
        motion="low-angle dolly tracking with confident forward energy",
    ),
    CAMERA_PRESET_ORBIT: CameraPanelPreset(
        name=CAMERA_PRESET_ORBIT,
        camera=CAMERA_PRESET_ORBIT,
        lens="50mm",
        lighting="soft wrap with specular separation",
        motion="controlled orbit around the subject to reveal shape and intent",
    ),
    CAMERA_PRESET_TRACKING: CameraPanelPreset(
        name=CAMERA_PRESET_TRACKING,
        camera=CAMERA_PRESET_TRACKING,
        lens="35mm",
        lighting="directional motivated light that travels with the subject",
        motion="side tracking move anchored to the scene objective",
    ),
    CAMERA_PRESET_CRANE: CameraPanelPreset(
        name=CAMERA_PRESET_CRANE,
        camera=CAMERA_PRESET_CRANE,
        lens="28mm",
        lighting="wide cinematic backlight with readable geography",
        motion="crane rise that expands scale without changing story intent",
    ),
    CAMERA_PRESET_DRONE: CameraPanelPreset(
        name=CAMERA_PRESET_DRONE,
        camera=CAMERA_PRESET_DRONE,
        lens="24mm",
        lighting="natural aerial light with preserved highlights",
        motion="aerial drift that establishes geography and production value",
    ),
    CAMERA_PRESET_STATIC: CameraPanelPreset(
        name=CAMERA_PRESET_STATIC,
        camera=CAMERA_PRESET_STATIC,
        lens="50mm",
        lighting="single motivated soft source with clean falloff",
        motion="locked-off composition; motion comes from performance inside frame",
    ),
}

IdFactory = Callable[[], str]
Clock = Callable[[], datetime]


def default_scene_id() -> str:
    return str(uuid4())


def default_clock() -> datetime:
    return datetime.now(UTC)


def _round_time(value: float) -> float:
    return round(value, TIMELINE_PRECISION_DIGITS)


def _duration(value: float) -> float:
    numeric = float(value)
    if numeric <= 0:
        return MINIMUM_SCENE_DURATION
    return _round_time(numeric)


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")


@dataclass(frozen=True)
class StoryboardScene:
    """Editable scene inside a PR006 StoryboardState."""

    id: str
    scene_number: int
    title: str
    objective: str
    emotion: str
    camera: str
    lens: str
    lighting: str
    motion: str
    duration: float
    environment: str
    mood: str
    lut: str
    prompt: str
    negative_prompt: str
    timeline_start: float = 0.0
    timeline_end: float = 0.0

    def __post_init__(self) -> None:
        if self.scene_number < FIRST_SCENE_NUMBER:
            raise ValueError("scene_number must be positive")
        object.__setattr__(self, "duration", _duration(self.duration))
        if self.timeline_start < 0 or self.timeline_end < 0:
            raise ValueError("timeline markers must be non-negative")
        for field_name in TEXT_SCENE_FIELDS:
            _require_text(getattr(self, field_name), field_name)

    @classmethod
    def from_shot(
        cls,
        shot: ShotPlan,
        *,
        scene_id: str,
        mood: MoodPreset,
    ) -> "StoryboardScene":
        return cls(
            id=scene_id,
            scene_number=shot.scene_number,
            title=shot.title,
            objective=shot.objective,
            emotion=shot.emotion,
            camera=shot.camera,
            lens=shot.lens,
            lighting=shot.lighting,
            motion=shot.motion,
            duration=shot.duration,
            environment=shot.environment,
            mood=mood.name,
            lut=mood.lut,
            prompt=shot.prompt,
            negative_prompt=shot.negative_prompt,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class StoryboardState:
    """Versioned state for editing a ProductionPlan storyboard."""

    project_id: str
    production_plan_id: str
    scenes: tuple[StoryboardScene, ...]
    version: int
    updated_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.project_id, "project_id")
        _require_text(self.production_plan_id, "production_plan_id")
        if self.version < INITIAL_STORYBOARD_VERSION:
            raise ValueError("version must be positive")
        if not isinstance(self.updated_at, datetime):
            raise ValueError("updated_at must be a datetime")
        if not isinstance(self.scenes, tuple):
            object.__setattr__(self, "scenes", tuple(self.scenes))
        if len(self.scenes) < MINIMUM_EDITOR_SCENES:
            raise ValueError("scenes are required")
        for scene in self.scenes:
            if not isinstance(scene, StoryboardScene):
                raise ValueError("scenes must contain StoryboardScene instances")
        object.__setattr__(self, "scenes", _renumber_and_timeline(self.scenes))

    @classmethod
    def from_production_plan(
        cls,
        plan: ProductionPlan,
        *,
        project_id: str,
        id_factory: IdFactory = default_scene_id,
        clock: Clock = default_clock,
        mood_engine: MoodEngine | None = None,
    ) -> "StoryboardState":
        engine = mood_engine or MoodEngine()
        mood = engine.resolve(plan.mood)
        scenes = tuple(
            StoryboardScene.from_shot(shot, scene_id=id_factory(), mood=mood)
            for shot in plan.shots
        )
        return cls(
            project_id=project_id,
            production_plan_id=plan.id,
            scenes=scenes,
            version=INITIAL_STORYBOARD_VERSION,
            updated_at=clock(),
        )

    @property
    def total_duration(self) -> float:
        return _round_time(sum(scene.duration for scene in self.scenes))

    @property
    def timeline(self) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "scene_id": scene.id,
                "scene_number": scene.scene_number,
                "start": scene.timeline_start,
                "duration": scene.duration,
                "end": scene.timeline_end,
            }
            for scene in self.scenes
        )

    def update_scene(self, scene_id: str, changes: Mapping[str, object], *, clock: Clock = default_clock) -> "StoryboardState":
        patch = {key: value for key, value in changes.items() if key in EDITABLE_SCENE_FIELDS}
        if not patch:
            return self
        scenes: list[StoryboardScene] = []
        changed = False
        for scene in self.scenes:
            if scene.id != scene_id:
                scenes.append(scene)
                continue
            changed = True
            if "duration" in patch:
                patch["duration"] = _duration(float(patch["duration"]))
            scenes.append(replace(scene, **patch))
        return self._advance(scenes, clock=clock) if changed else self

    def reorder_scene(self, source_scene_id: str, target_scene_id: str, *, clock: Clock = default_clock) -> "StoryboardState":
        source_index = self._index_of(source_scene_id)
        target_index = self._index_of(target_scene_id)
        if source_index is None or target_index is None or source_index == target_index:
            return self
        scenes = list(self.scenes)
        moved = scenes.pop(source_index)
        scenes.insert(target_index, moved)
        return self._advance(scenes, clock=clock)

    def duplicate_scene(
        self,
        scene_id: str,
        *,
        id_factory: IdFactory = default_scene_id,
        clock: Clock = default_clock,
    ) -> "StoryboardState":
        scene_index = self._index_of(scene_id)
        if scene_index is None:
            return self
        scenes = list(self.scenes)
        duplicate = replace(scenes[scene_index], id=id_factory())
        scenes.insert(scene_index + 1, duplicate)
        return self._advance(scenes, clock=clock)

    def remove_scene(self, scene_id: str, *, clock: Clock = default_clock) -> "StoryboardState":
        if len(self.scenes) <= MINIMUM_EDITOR_SCENES:
            return self
        scenes = [scene for scene in self.scenes if scene.id != scene_id]
        return self._advance(scenes, clock=clock) if len(scenes) != len(self.scenes) else self

    def apply_camera_preset(
        self,
        scene_id: str,
        preset_name: str,
        *,
        clock: Clock = default_clock,
    ) -> "StoryboardState":
        preset = CAMERA_PANEL_PRESETS[preset_name]
        return self.update_scene(
            scene_id,
            {
                "camera": preset.camera,
                "lens": preset.lens,
                "lighting": preset.lighting,
                "motion": preset.motion,
            },
            clock=clock,
        )

    def apply_mood(
        self,
        scene_id: str,
        mood: str,
        *,
        clock: Clock = default_clock,
        mood_engine: MoodEngine | None = None,
    ) -> "StoryboardState":
        preset = (mood_engine or MoodEngine()).resolve(mood)
        scenes: list[StoryboardScene] = []
        changed = False
        for scene in self.scenes:
            if scene.id != scene_id:
                scenes.append(scene)
                continue
            changed = True
            scenes.append(replace(scene, mood=preset.name, lut=preset.lut))
        return self._advance(scenes, clock=clock) if changed else self

    def _index_of(self, scene_id: str) -> int | None:
        for index, scene in enumerate(self.scenes):
            if scene.id == scene_id:
                return index
        return None

    def _advance(self, scenes: list[StoryboardScene] | tuple[StoryboardScene, ...], *, clock: Clock) -> "StoryboardState":
        return replace(
            self,
            scenes=tuple(scenes),
            version=self.version + 1,
            updated_at=clock(),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "production_plan_id": self.production_plan_id,
            "scenes": [scene.to_dict() for scene in self.scenes],
            "version": self.version,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class StoryboardHistory:
    """Undo/redo ring for PR006 storyboard edits."""

    present: StoryboardState
    past: tuple[StoryboardState, ...] = ()
    future: tuple[StoryboardState, ...] = ()
    limit: int = STORYBOARD_HISTORY_LIMIT

    def __post_init__(self) -> None:
        if self.limit <= 0:
            raise ValueError("limit must be positive")
        if not isinstance(self.present, StoryboardState):
            raise ValueError("present must be a StoryboardState")

    def commit(self, state: StoryboardState) -> "StoryboardHistory":
        if state.version == self.present.version:
            return self
        return replace(
            self,
            past=(*self.past, self.present)[-self.limit :],
            present=state,
            future=(),
        )

    def undo(self) -> "StoryboardHistory":
        if not self.past:
            return self
        return replace(
            self,
            past=self.past[:-1],
            present=self.past[-1],
            future=(self.present, *self.future)[: self.limit],
        )

    def redo(self) -> "StoryboardHistory":
        if not self.future:
            return self
        return replace(
            self,
            past=(*self.past, self.present)[-self.limit :],
            present=self.future[0],
            future=self.future[1:],
        )


def _renumber_and_timeline(scenes: tuple[StoryboardScene, ...] | list[StoryboardScene]) -> tuple[StoryboardScene, ...]:
    cursor = 0.0
    normalized: list[StoryboardScene] = []
    for offset, scene in enumerate(scenes):
        start = _round_time(cursor)
        duration = _duration(scene.duration)
        cursor += duration
        normalized.append(
            replace(
                scene,
                scene_number=FIRST_SCENE_NUMBER + offset,
                duration=duration,
                timeline_start=start,
                timeline_end=_round_time(cursor),
            )
        )
    return tuple(normalized)


__all__ = [
    "CAMERA_PANEL_PRESETS",
    "CAMERA_PRESET_CRANE",
    "CAMERA_PRESET_DRONE",
    "CAMERA_PRESET_HERO_WALK",
    "CAMERA_PRESET_ORBIT",
    "CAMERA_PRESET_STATIC",
    "CAMERA_PRESET_TRACKING",
    "EDITABLE_SCENE_FIELDS",
    "MOOD_NAMES",
    "STORYBOARD_HISTORY_LIMIT",
    "CameraPanelPreset",
    "StoryboardHistory",
    "StoryboardScene",
    "StoryboardState",
]
