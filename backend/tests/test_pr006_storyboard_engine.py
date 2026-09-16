from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from app.core.director import (
    CAMERA_PANEL_PRESETS,
    STORYBOARD_HISTORY_LIMIT,
    ProductionPlan,
    ShotPlan,
    StoryboardHistory,
    StoryboardScene,
    StoryboardState,
)

BASE_TIME = datetime(2026, 9, 15, tzinfo=UTC)


def clock(offset: int = 0):
    return lambda: BASE_TIME + timedelta(seconds=offset)


def ids(*values: str):
    remaining = list(values)

    def factory() -> str:
        return remaining.pop(0) if remaining else f"scene-{len(values) + 1}"

    return factory


def shot(number: int, duration: float) -> ShotPlan:
    return ShotPlan(
        scene_number=number,
        title=f"Cena {number}",
        objective=f"Objetivo narrativo {number}",
        emotion=f"emoção {number}",
        camera="Static" if number > 1 else "Drone",
        lens="50mm",
        lighting="motivated cinematic light",
        motion="motion motivated by the beat",
        duration=duration,
        prompt=f"prompt planejado {number}",
        negative_prompt="no incoherent cuts",
        environment=f"ambiente {number}",
    )


def production_plan() -> ProductionPlan:
    return ProductionPlan(
        id="prod-pr006",
        title="PR006 Storyboard",
        concept="visual storyboard editing",
        mood="Minimal",
        audience="studio audience",
        platform="web",
        duration=20,
        style="neutral filmic LUT",
        music="ambient pulse",
        voice="natural confident narration",
        persona_id=None,
        shots=(shot(1, 2), shot(2, 4), shot(3, 6), shot(4, 8)),
        created_at=BASE_TIME,
    )


def state() -> StoryboardState:
    return StoryboardState.from_production_plan(
        production_plan(),
        project_id="project-pr006",
        id_factory=ids("s1", "s2", "s3", "s4"),
        clock=clock(),
    )


def test_storyboard_state_is_versioned_and_timeline_is_persisted() -> None:
    current = state()

    assert current.project_id == "project-pr006"
    assert current.production_plan_id == "prod-pr006"
    assert current.version == 1
    assert current.updated_at == BASE_TIME
    assert [scene.id for scene in current.scenes] == ["s1", "s2", "s3", "s4"]
    assert [scene.scene_number for scene in current.scenes] == [1, 2, 3, 4]
    assert [(scene.timeline_start, scene.timeline_end) for scene in current.scenes] == [
        (0.0, 2.0),
        (2.0, 6.0),
        (6.0, 12.0),
        (12.0, 20.0),
    ]
    assert current.total_duration == 20
    assert current.timeline[1] == {
        "scene_id": "s2",
        "scene_number": 2,
        "start": 2.0,
        "duration": 4.0,
        "end": 6.0,
    }


def test_storyboard_state_and_scene_are_immutable() -> None:
    current = state()

    with pytest.raises(FrozenInstanceError):
        current.version = 99
    with pytest.raises(FrozenInstanceError):
        current.scenes[0].title = "mutated"


def test_scene_update_changes_only_requested_scene_fields() -> None:
    current = state()
    updated = current.update_scene(
        "s2",
        {"title": "Novo título", "objective": "Novo objetivo", "prompt": "ignored"},
        clock=clock(2),
    )

    assert updated.version == 2
    assert updated.updated_at == BASE_TIME + timedelta(seconds=2)
    assert updated.scenes[1].title == "Novo título"
    assert updated.scenes[1].objective == "Novo objetivo"
    assert updated.scenes[1].prompt == current.scenes[1].prompt
    assert updated.scenes[0] == current.scenes[0]
    assert updated.scenes[2] == current.scenes[2]


def test_scene_update_sanitizes_duration_and_recomputes_timeline() -> None:
    current = state()
    updated = current.update_scene("s1", {"duration": 7.456}, clock=clock(3))

    assert updated.version == 2
    assert updated.scenes[0].duration == 7.46
    assert updated.scenes[0].timeline_end == 7.46
    assert updated.scenes[1].timeline_start == 7.46
    assert updated.total_duration == 25.46

    sanitized = updated.update_scene("s1", {"duration": -5}, clock=clock(4))
    assert sanitized.scenes[0].duration == 0.1


def test_drag_reorder_updates_scene_numbers_timeline_and_total_duration() -> None:
    current = state()
    reordered = current.reorder_scene("s4", "s2", clock=clock(5))

    assert reordered.version == 2
    assert [scene.id for scene in reordered.scenes] == ["s1", "s4", "s2", "s3"]
    assert [scene.scene_number for scene in reordered.scenes] == [1, 2, 3, 4]
    assert [scene.timeline_start for scene in reordered.scenes] == [0.0, 2.0, 10.0, 14.0]
    assert reordered.total_duration == current.total_duration


def test_noop_operations_do_not_increment_version() -> None:
    current = state()

    assert current.update_scene("missing", {"title": "x"}) is current
    assert current.update_scene("s1", {"prompt": "not editable"}) is current
    assert current.reorder_scene("s1", "s1") is current
    assert current.reorder_scene("missing", "s1") is current
    assert current.duplicate_scene("missing") is current
    assert current.remove_scene("missing") is current
    assert current.apply_mood("missing", "Epic") is current


def test_camera_panel_preset_updates_only_camera_director_slice() -> None:
    current = state()
    updated = current.apply_camera_preset("s3", "Hero Walk", clock=clock(6))

    assert updated.version == 2
    assert set(CAMERA_PANEL_PRESETS) == {"Hero Walk", "Orbit", "Tracking", "Crane", "Drone", "Static"}
    assert updated.scenes[2].camera == "Hero Walk"
    assert updated.scenes[2].lens == "35mm anamorphic"
    assert "dolly tracking" in updated.scenes[2].motion
    assert updated.scenes[2].lighting == "motivated hero key with controlled rim light"
    assert updated.scenes[2].objective == current.scenes[2].objective
    assert updated.scenes[2].mood == current.scenes[2].mood


def test_mood_panel_updates_only_scene_mood_and_lut() -> None:
    current = state()
    updated = current.apply_mood("s2", "Neo", clock=clock(7))

    assert updated.version == 2
    assert updated.scenes[1].mood == "Neo"
    assert updated.scenes[1].lut == "saturated cyan-magenta neo-city LUT"
    assert updated.scenes[1].camera == current.scenes[1].camera
    assert updated.scenes[1].lens == current.scenes[1].lens
    assert updated.scenes[0].mood == "Minimal"


def test_duplicate_scene_receives_new_uuid_and_keeps_camera_and_mood() -> None:
    current = state().apply_mood("s2", "Luxury", clock=clock(8))
    duplicated = current.duplicate_scene("s2", id_factory=ids("uuid-copy"), clock=clock(9))

    assert duplicated.version == 3
    assert [scene.id for scene in duplicated.scenes] == ["s1", "s2", "uuid-copy", "s3", "s4"]
    copy = duplicated.scenes[2]
    assert copy.scene_number == 3
    assert copy.camera == current.scenes[1].camera
    assert copy.mood == "Luxury"
    assert copy.lut == current.scenes[1].lut
    assert copy.prompt == current.scenes[1].prompt


def test_remove_scene_renumbers_but_keeps_at_least_one_scene() -> None:
    current = state()
    removed = current.remove_scene("s1", clock=clock(10))

    assert removed.version == 2
    assert [scene.id for scene in removed.scenes] == ["s2", "s3", "s4"]
    assert [scene.scene_number for scene in removed.scenes] == [1, 2, 3]
    assert removed.scenes[0].timeline_start == 0

    one_scene = StoryboardState(
        project_id="project-pr006",
        production_plan_id="prod-pr006",
        scenes=(current.scenes[0],),
        version=1,
        updated_at=BASE_TIME,
    )
    assert one_scene.remove_scene("s1") is one_scene


def test_undo_and_redo_track_edit_reorder_duplicate_and_remove() -> None:
    history = StoryboardHistory(state())
    history = history.commit(history.present.update_scene("s1", {"title": "Editada"}, clock=clock(11)))
    history = history.commit(history.present.reorder_scene("s4", "s2", clock=clock(12)))
    history = history.commit(history.present.duplicate_scene("s4", id_factory=ids("s4-copy"), clock=clock(13)))
    history = history.commit(history.present.remove_scene("s1", clock=clock(14)))

    assert history.present.version == 5
    history = history.undo()
    assert "s1" in [scene.id for scene in history.present.scenes]
    history = history.undo()
    assert "s4-copy" not in [scene.id for scene in history.present.scenes]
    history = history.redo()
    assert "s4-copy" in [scene.id for scene in history.present.scenes]
    history = history.redo()
    assert "s1" not in [scene.id for scene in history.present.scenes]


def test_history_keeps_a_maximum_of_50_states_and_noops_do_not_commit() -> None:
    history = StoryboardHistory(state())
    assert history.commit(history.present) is history

    for index in range(STORYBOARD_HISTORY_LIMIT + 5):
        history = history.commit(
            history.present.update_scene("s1", {"title": f"Edit {index}"}, clock=clock(20 + index))
        )

    assert len(history.past) == STORYBOARD_HISTORY_LIMIT
    assert history.present.version == STORYBOARD_HISTORY_LIMIT + 6
    assert len(history.future) == 0


def test_history_validates_limit_and_present_state() -> None:
    with pytest.raises(ValueError, match="limit"):
        StoryboardHistory(state(), limit=0)
    with pytest.raises(ValueError, match="present"):
        StoryboardHistory("not-a-state")  # type: ignore[arg-type]


def test_storyboard_state_validates_required_fields() -> None:
    current = state()
    with pytest.raises(ValueError, match="project_id"):
        StoryboardState("", "prod", current.scenes, 1, BASE_TIME)
    with pytest.raises(ValueError, match="version"):
        StoryboardState("project", "prod", current.scenes, 0, BASE_TIME)
    with pytest.raises(ValueError, match="updated_at"):
        StoryboardState("project", "prod", current.scenes, 1, "now")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="scenes are required"):
        StoryboardState("project", "prod", (), 1, BASE_TIME)
    with pytest.raises(ValueError, match="StoryboardScene"):
        StoryboardState("project", "prod", (object(),), 1, BASE_TIME)  # type: ignore[arg-type]


def test_storyboard_scene_validates_required_fields_and_serializes() -> None:
    current = state()
    payload = current.scenes[0].to_dict()

    assert payload["id"] == "s1"
    assert current.to_dict()["updated_at"] == BASE_TIME.isoformat()
    with pytest.raises(ValueError, match="id"):
        StoryboardScene(
            id="",
            scene_number=1,
            title="title",
            objective="objective",
            emotion="emotion",
            camera="Static",
            lens="50mm",
            lighting="light",
            motion="still",
            duration=1,
            environment="studio",
            mood="Minimal",
            lut="neutral LUT",
            prompt="prompt",
            negative_prompt="negative",
        )
    with pytest.raises(ValueError, match="scene_number"):
        StoryboardScene(
            id="scene",
            scene_number=0,
            title="title",
            objective="objective",
            emotion="emotion",
            camera="Static",
            lens="50mm",
            lighting="light",
            motion="still",
            duration=1,
            environment="studio",
            mood="Minimal",
            lut="neutral LUT",
            prompt="prompt",
            negative_prompt="negative",
        )
    with pytest.raises(ValueError, match="timeline"):
        StoryboardScene(
            id="scene",
            scene_number=1,
            title="title",
            objective="objective",
            emotion="emotion",
            camera="Static",
            lens="50mm",
            lighting="light",
            motion="still",
            duration=1,
            environment="studio",
            mood="Minimal",
            lut="neutral LUT",
            prompt="prompt",
            negative_prompt="negative",
            timeline_start=-1,
        )
