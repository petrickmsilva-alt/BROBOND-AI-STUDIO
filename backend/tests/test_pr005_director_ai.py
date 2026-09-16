"""PR005 — Director AI Engine: production planning only."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app.core.director import CameraDirector, DirectorAgent, MoodEngine, ProductionPlan, ShotPlan
from app.core.director.camera_director import CAMERA_TYPES
from app.core.director.director_agent import MAX_STORYBOARD_SCENES, MIN_STORYBOARD_SCENES
from app.core.director.mood_config import MOOD_NAMES
from app.core.shot_library import ShotLibrary
from app.main import app, production_director_agent

client = TestClient(app)


def test_production_director_is_wired_once_at_the_boundary() -> None:
    assert isinstance(production_director_agent, DirectorAgent)


@pytest.fixture()
def sample_shot() -> ShotPlan:
    return ShotPlan(
        scene_number=1,
        title="Cena de abertura",
        objective="Estabelecer o mundo",
        emotion="curiosidade",
        camera="Drone",
        lens="24mm",
        lighting="soft volumetric key",
        motion="aerial reveal",
        duration=3.5,
        prompt="a directed scene prompt",
        negative_prompt="no incoherent geography",
        environment="city at blue hour",
    )


def test_shot_plan_requires_every_storyboard_field(sample_shot: ShotPlan) -> None:
    payload = sample_shot.to_dict()
    for field in (
        "scene_number",
        "title",
        "objective",
        "emotion",
        "camera",
        "lens",
        "lighting",
        "motion",
        "duration",
        "prompt",
        "negative_prompt",
        "environment",
    ):
        assert field in payload

    with pytest.raises(ValueError, match="objective is required"):
        ShotPlan(**{**payload, "objective": "   "})
    with pytest.raises(ValueError, match="scene_number"):
        ShotPlan(**{**payload, "scene_number": 0})
    with pytest.raises(ValueError, match="duration"):
        ShotPlan(**{**payload, "duration": 0})


def test_production_plan_is_immutable_and_central(sample_shot: ShotPlan) -> None:
    plan = ProductionPlan(
        id="prod_test",
        title="Plano teste",
        concept="Um conceito cinematográfico",
        mood="Luxury",
        audience="social audience",
        platform="instagram",
        duration=12.0,
        style="champagne LUT",
        music="minimal pulse",
        voice="calm voice",
        persona_id="persona-1",
        shots=[sample_shot],  # type: ignore[arg-type]
        created_at=datetime.now(UTC),
    )

    assert isinstance(plan.shots, tuple)
    assert plan.scene_count == 1
    assert plan.to_dict()["shots"][0]["camera"] == "Drone"
    with pytest.raises(FrozenInstanceError):
        plan.title = "mutated"  # type: ignore[misc]


def test_production_plan_rejects_empty_required_fields(sample_shot: ShotPlan) -> None:
    valid = {
        "id": "prod_test",
        "title": "title",
        "concept": "concept",
        "mood": "Luxury",
        "audience": "audience",
        "platform": "web",
        "duration": 8.0,
        "style": "style",
        "music": "music",
        "voice": "voice",
        "persona_id": None,
        "shots": (sample_shot,),
        "created_at": datetime.now(UTC),
    }
    with pytest.raises(ValueError, match="title is required"):
        ProductionPlan(**{**valid, "title": ""})
    with pytest.raises(ValueError, match="shots"):
        ProductionPlan(**{**valid, "shots": ()})
    with pytest.raises(ValueError, match="duration"):
        ProductionPlan(**{**valid, "duration": 0})
    with pytest.raises(ValueError, match="created_at"):
        ProductionPlan(**{**valid, "created_at": "now"})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="ShotPlan"):
        ProductionPlan(**{**valid, "shots": (object(),)})  # type: ignore[arg-type]


def test_mood_engine_exposes_the_six_internal_presets() -> None:
    engine = MoodEngine()
    presets = engine.presets()
    assert [preset.name for preset in presets] == list(MOOD_NAMES)
    for preset in presets:
        data = preset.to_dict()
        assert data["lut"]
        assert data["contrast"]
        assert data["lighting"]
        assert data["temperature"]
        assert data["rhythm"]
        assert data["particles"]


def test_mood_engine_resolves_aliases_and_defaults() -> None:
    engine = MoodEngine()
    assert engine.resolve("luxo").name == "Luxury"
    assert engine.resolve(user_intent="campanha neon futurista").name == "Neo"
    assert engine.resolve("not-a-mood").name == "Minimal"


def test_camera_director_uses_the_existing_shot_library() -> None:
    library = ShotLibrary()
    director = CameraDirector(library)

    assert director.available_camera_types() == CAMERA_TYPES
    sequence = director.sequence(scene_count=6, mood="Epic", platform="cinema")
    assert {choice.camera for choice in sequence} >= {"Dolly", "Orbit", "Crane", "Tracking", "Static", "Drone"}
    assert all(choice.lens.endswith("mm") for choice in sequence)
    assert all(library.get(choice.shot_code) is not None for choice in sequence)


def test_camera_director_keeps_choices_editable_and_platform_aware() -> None:
    director = CameraDirector(ShotLibrary())
    vertical_hook = director.choose(scene_number=1, scene_count=4, platform="tiktok")
    minimal_open = director.choose(scene_number=1, scene_count=4, mood="Minimal", platform="cinema")

    assert vertical_hook.camera == "Tracking"
    assert minimal_open.camera == "Static"
    assert vertical_hook.to_dict()["motion"]
    assert minimal_open.lighting


def test_camera_director_has_a_safe_fallback_when_the_library_is_empty() -> None:
    class EmptyLibrary:
        def all(self):
            return ()

    choice = CameraDirector(EmptyLibrary()).choose(scene_number=1, scene_count=4)  # type: ignore[arg-type]
    assert choice.camera in CAMERA_TYPES
    assert choice.lens == "50mm"
    assert choice.shot_code == ""


def test_director_agent_creates_a_complete_production_plan() -> None:
    plan = DirectorAgent().create_production_plan(
        user_intent="Campanha de luxo para uma jaqueta artesanal",
        persona_id="persona-42",
        platform="instagram",
        duration=30,
        mood="Luxury",
    )

    assert isinstance(plan, ProductionPlan)
    assert plan.mood == "Luxury"
    assert plan.persona_id == "persona-42"
    assert MIN_STORYBOARD_SCENES <= plan.scene_count <= MAX_STORYBOARD_SCENES
    assert sum(shot.duration for shot in plan.shots) == pytest.approx(plan.duration)
    assert len({shot.duration for shot in plan.shots}) > 1
    assert len({shot.objective for shot in plan.shots}) == plan.scene_count
    assert all(shot.prompt and shot.negative_prompt for shot in plan.shots)


def test_director_agent_infers_mood_and_scales_storyboard_length() -> None:
    agent = DirectorAgent()
    short = agent.create_production_plan("vídeo sport de treino", None, "reels", 10)
    long = agent.create_production_plan("filme neo sobre uma cidade viva", None, "youtube", 120)
    symbolic = agent.create_production_plan("!!!", None, "", None)

    assert short.mood == "Sport"
    assert short.scene_count == MIN_STORYBOARD_SCENES
    assert long.mood == "Neo"
    assert long.scene_count == MAX_STORYBOARD_SCENES
    assert symbolic.title == "Untitled Production"
    assert symbolic.duration == 30


def test_director_agent_rejects_empty_intent_and_invalid_duration() -> None:
    agent = DirectorAgent()
    with pytest.raises(ValueError, match="user_intent"):
        agent.create_production_plan(" ", None, "web", 20)
    with pytest.raises(ValueError, match="duration"):
        agent.create_production_plan("uma campanha", None, "web", 0)


def test_director_agent_does_not_import_or_call_providers() -> None:
    probe = """
import sys
sys.path.insert(0, {backend_root!r})
from app.core.director import DirectorAgent
DirectorAgent().create_production_plan('minimal brand film', None, 'web', 20)
print(any(name.startswith('app.providers') for name in sys.modules))
"""
    result = subprocess.run(
        [sys.executable, "-c", probe.format(backend_root=str(app_root() / "backend"))],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


def test_production_plan_route_returns_storyboard_cards_and_no_job_contract() -> None:
    response = client.post(
        "/api/v1/core/director/production-plan",
        json={
            "user_intent": "Criar um comercial épico para tênis de corrida",
            "persona_id": "persona-route",
            "platform": "youtube",
            "duration": 45,
            "mood": "Epic",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mood"] == "Epic"
    assert body["persona_id"] == "persona-route"
    assert 4 <= len(body["shots"]) <= 8
    assert "scene_count" not in body
    assert "output_url" not in body
    assert "job_id" not in body
    assert all({"scene_number", "objective", "camera", "lens", "duration", "emotion"} <= set(shot) for shot in body["shots"])


def test_production_plan_route_validates_empty_intent() -> None:
    response = client.post(
        "/api/v1/core/director/production-plan",
        json={"user_intent": "", "platform": "web", "duration": 30, "mood": "Minimal"},
    )
    assert response.status_code == 422


def test_director_page_contains_the_pr005_controls() -> None:
    source = (app_root() / "app" / "studio" / "director" / "page.tsx").read_text(encoding="utf-8")
    for label in (
        "O que você quer criar hoje?",
        "Persona",
        "Plataforma",
        "Duração",
        "Mood",
        "Criar Produção",
    ):
        assert label in source
    assert "createProductionPlan(" in source
    assert "createImageJob(" not in source
    assert "createVideoJob(" not in source


def test_director_page_renders_editable_storyboard_fields() -> None:
    director_dir = app_root() / "app" / "studio" / "director"
    source = "\n".join(path.read_text(encoding="utf-8") for path in director_dir.glob("*.tsx"))
    for card_field in ("Cena", "Objetivo", "Câmera", "Lente", "Duração", "Emoção"):
        assert card_field in source
    assert "updateScene(" in source
    assert "onDurationChange" in source


def app_root():
    from pathlib import Path

    return Path(__file__).resolve().parents[2]
