"""CameraDirector — chooses editable camera language from the shot library."""
from __future__ import annotations

from dataclasses import dataclass

from ..contracts import ShotPreset
from ..shot_library import ShotLibrary
from .shot_plan import FIRST_SCENE_NUMBER

CAMERA_DOLLY = "Dolly"
CAMERA_ORBIT = "Orbit"
CAMERA_CRANE = "Crane"
CAMERA_TRACKING = "Tracking"
CAMERA_STATIC = "Static"
CAMERA_DRONE = "Drone"

CAMERA_TYPES: tuple[str, ...] = (
    CAMERA_DOLLY,
    CAMERA_ORBIT,
    CAMERA_CRANE,
    CAMERA_TRACKING,
    CAMERA_STATIC,
    CAMERA_DRONE,
)

SCENE_COUNT_FOUR = 4
SCENE_COUNT_FIVE = 5
SCENE_COUNT_SIX = 6
SCENE_COUNT_SEVEN = 7
SCENE_COUNT_EIGHT = 8

CAMERA_ARCS: dict[int, tuple[str, ...]] = {
    SCENE_COUNT_FOUR: (CAMERA_DRONE, CAMERA_DOLLY, CAMERA_ORBIT, CAMERA_STATIC),
    SCENE_COUNT_FIVE: (CAMERA_DRONE, CAMERA_DOLLY, CAMERA_TRACKING, CAMERA_ORBIT, CAMERA_STATIC),
    SCENE_COUNT_SIX: (CAMERA_DRONE, CAMERA_DOLLY, CAMERA_TRACKING, CAMERA_ORBIT, CAMERA_CRANE, CAMERA_STATIC),
    SCENE_COUNT_SEVEN: (CAMERA_DRONE, CAMERA_DOLLY, CAMERA_TRACKING, CAMERA_ORBIT, CAMERA_STATIC, CAMERA_CRANE, CAMERA_DOLLY),
    SCENE_COUNT_EIGHT: (CAMERA_DRONE, CAMERA_DOLLY, CAMERA_TRACKING, CAMERA_ORBIT, CAMERA_STATIC, CAMERA_CRANE, CAMERA_DOLLY, CAMERA_STATIC),
}

CAMERA_QUERY_TERMS: dict[str, tuple[str, ...]] = {
    CAMERA_DOLLY: ("dolly",),
    CAMERA_ORBIT: ("orbit", "rotation", "revolution"),
    CAMERA_CRANE: ("crane", "lift"),
    CAMERA_TRACKING: ("tracking", "track", "following"),
    CAMERA_STATIC: ("static", "locked tripod", "held long"),
    CAMERA_DRONE: ("drone", "aerial"),
}

FAMILY_PREFERENCE_BY_CAMERA: dict[str, tuple[str, ...]] = {
    CAMERA_DRONE: ("establishing", "atmosphere"),
    CAMERA_DOLLY: ("product", "introduction", "fashion"),
    CAMERA_TRACKING: ("action", "documentary"),
    CAMERA_ORBIT: ("fashion", "product", "intimacy"),
    CAMERA_CRANE: ("resolution", "establishing"),
    CAMERA_STATIC: ("intimacy", "dialogue", "product"),
}

FALLBACK_LENS = "50mm"
FALLBACK_LIGHTING = "motivated cinematic light"
FALLBACK_MOTION = "motivated stillness"


@dataclass(frozen=True)
class CameraDirection:
    """Editable camera decision derived from a ShotPreset."""

    camera: str
    lens: str
    lighting: str
    motion: str
    shot_name: str
    shot_code: str

    def to_dict(self) -> dict[str, str]:
        return {
            "camera": self.camera,
            "lens": self.lens,
            "lighting": self.lighting,
            "motion": self.motion,
            "shot_name": self.shot_name,
            "shot_code": self.shot_code,
        }


class CameraDirector:
    """Selects Dolly, Orbit, Crane, Tracking, Static or Drone from ShotLibrary."""

    def __init__(self, shot_library: ShotLibrary | None = None) -> None:
        self._shot_library = shot_library or ShotLibrary()

    def available_camera_types(self) -> tuple[str, ...]:
        return CAMERA_TYPES

    def choose(
        self,
        *,
        scene_number: int,
        scene_count: int,
        objective: str = "",
        emotion: str = "",
        mood: str = "",
        platform: str = "",
    ) -> CameraDirection:
        """Choose one editable camera direction for a storyboard scene."""

        camera = self._camera_for_scene(scene_number=scene_number, scene_count=scene_count, platform=platform, mood=mood)
        shot = self._select_shot(camera, scene_number=scene_number, objective=objective, emotion=emotion)
        if shot is None:
            return CameraDirection(
                camera=camera,
                lens=FALLBACK_LENS,
                lighting=FALLBACK_LIGHTING,
                motion=FALLBACK_MOTION,
                shot_name="Fallback Direction",
                shot_code="",
            )
        return CameraDirection(
            camera=camera,
            lens=shot.lens,
            lighting=shot.lighting or FALLBACK_LIGHTING,
            motion=shot.camera_path,
            shot_name=shot.name,
            shot_code=shot.code,
        )

    def sequence(self, *, scene_count: int, mood: str = "", platform: str = "") -> tuple[CameraDirection, ...]:
        return tuple(
            self.choose(
                scene_number=scene_number,
                scene_count=scene_count,
                mood=mood,
                platform=platform,
            )
            for scene_number in range(FIRST_SCENE_NUMBER, scene_count + FIRST_SCENE_NUMBER)
        )

    def _camera_for_scene(self, *, scene_number: int, scene_count: int, platform: str, mood: str) -> str:
        arc = CAMERA_ARCS.get(scene_count) or CAMERA_ARCS[SCENE_COUNT_EIGHT]
        index = max(scene_number - FIRST_SCENE_NUMBER, FIRST_SCENE_NUMBER - FIRST_SCENE_NUMBER)
        camera = arc[index % len(arc)]
        if scene_number == FIRST_SCENE_NUMBER and platform.strip().casefold() in {"reels", "tiktok", "shorts"}:
            return CAMERA_TRACKING
        if mood.strip().casefold() == "minimal" and camera == CAMERA_DRONE:
            return CAMERA_STATIC
        return camera

    def _select_shot(self, camera: str, *, scene_number: int, objective: str, emotion: str) -> ShotPreset | None:
        candidates = self._candidates(camera)
        if not candidates:
            return None
        preferred = self._prefer_families(candidates, FAMILY_PREFERENCE_BY_CAMERA.get(camera, ()))
        scored = sorted(
            preferred,
            key=lambda shot: (
                self._matches_text(shot, objective),
                self._matches_text(shot, emotion),
                shot.code,
            ),
            reverse=True,
        )
        index = (scene_number - FIRST_SCENE_NUMBER) % len(scored)
        return scored[index]

    def _candidates(self, camera: str) -> list[ShotPreset]:
        terms = CAMERA_QUERY_TERMS[camera]
        found: list[ShotPreset] = []
        for shot in self._shot_library.all():
            haystack = " ".join((shot.name, shot.camera_path, shot.family, shot.intention)).casefold()
            if any(term in haystack for term in terms):
                found.append(shot)
        return found

    @staticmethod
    def _prefer_families(candidates: list[ShotPreset], families: tuple[str, ...]) -> list[ShotPreset]:
        preferred = [shot for shot in candidates if shot.family in families]
        return preferred or candidates

    @staticmethod
    def _matches_text(shot: ShotPreset, text: str) -> bool:
        needle = text.strip().casefold()
        if not needle:
            return False
        haystack = " ".join((shot.name, shot.family, shot.intention, shot.continuity)).casefold()
        return any(word for word in needle.split() if word in haystack)
