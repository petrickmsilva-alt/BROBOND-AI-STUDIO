"""ETAPA 8 tests — the storyboard endpoint.

`POST /api/v1/core/storyboard` is additive. The pre-existing
`POST /api/v1/storyboards/expand` is asserted here too, so that the guard fails
loudly if anything about it changes.
"""
from __future__ import annotations

import ast
import pathlib

import pytest
from fastapi.testclient import TestClient

from app.main import app

BRIEF = "Quero um comercial de 30 segundos para uma camiseta artesanal."


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# The new endpoint
# ---------------------------------------------------------------------------


def test_a_brief_comes_back_cast_into_real_shots(client):
    body = client.post("/api/v1/core/storyboard", json={"brief": BRIEF, "scene_count": 5}).json()
    assert body["scene_count"] == 5
    assert len(body["shots"]) == 5
    assert body["shot_codes"] == ["SH002", "SH028", "SH157", "SH158", "SH253"]
    assert body["valid"] is True
    assert body["violations"] == []


def test_every_scene_carries_the_direction_that_comes_with_its_shot(client):
    shot = client.post(
        "/api/v1/core/storyboard", json={"brief": BRIEF, "scene_count": 5}
    ).json()["shots"][0]
    assert shot["shot_code"] == "SH002"
    assert shot["shot_name"] == "City Wakes"
    assert shot["lens"] == "24mm"
    assert shot["lighting"] == "blue hour ambience, soft volumetric key"
    assert shot["continuity"]


def test_the_lens_progression_is_visible_without_recounting_it(client):
    body = client.post("/api/v1/core/storyboard", json={"brief": BRIEF, "scene_count": 5}).json()
    assert body["lens_progression"] == ["24mm", "50mm", "85mm", "135mm", "24mm"]
    assert body["family_sequence"] == [
        "establishing",
        "introduction",
        "product",
        "product",
        "resolution",
    ]


def test_runtime_is_reported_at_the_top_level(client):
    body = client.post(
        "/api/v1/core/storyboard",
        json={"brief": BRIEF, "scene_count": 4, "duration_per_scene": 2.5},
    ).json()
    assert body["runtime_seconds"] == pytest.approx(10.0)


def test_the_beat_sheet_is_returned_for_a_director_to_read(client):
    sheet = client.post(
        "/api/v1/core/storyboard", json={"brief": BRIEF, "scene_count": 3}
    ).json()["beat_sheet"]
    assert sheet.startswith("COMMERCIAL — 3 scenes")
    assert "SH002" in sheet


def test_a_long_sequence_still_casts_distinct_shots(client):
    body = client.post("/api/v1/core/storyboard", json={"brief": BRIEF, "scene_count": 12}).json()
    assert len(set(body["shot_codes"])) == 12
    assert body["valid"] is True


def test_a_broken_sequence_reports_what_is_wrong_rather_than_failing(client):
    """30s x 12 scenes is over the ceiling; the endpoint says so, it does not 500."""

    body = client.post(
        "/api/v1/core/storyboard",
        json={"brief": BRIEF, "scene_count": 12, "duration_per_scene": 30.0},
    ).json()
    assert body["valid"] is False
    assert "runtime" in {finding["rule"] for finding in body["violations"]}


def test_style_and_persona_pass_through_to_the_director(client):
    body = client.post(
        "/api/v1/core/storyboard",
        json={"brief": BRIEF, "scene_count": 3, "persona": "CHAR_PETRICK", "style": "neo-tokyo"},
    ).json()
    assert body["scene_count"] == 3
    assert body["valid"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"brief": ""},
        {"brief": "x", "scene_count": 1},
        {"brief": "x", "scene_count": 40},
        {"brief": "x", "duration_per_scene": 0},
        {"brief": "x", "duration_per_scene": 999},
    ],
)
def test_out_of_range_requests_are_refused_before_reaching_the_engine(client, payload):
    assert client.post("/api/v1/core/storyboard", json=payload).status_code == 422


def test_a_missing_brief_is_refused(client):
    assert client.post("/api/v1/core/storyboard", json={}).status_code == 422


def test_the_engine_is_the_only_thing_building_the_storyboard():
    """No direction logic in the route — it delegates and serialises."""

    source = pathlib.Path("backend/app/main.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "build_core_storyboard":
            called = {
                n.func.id
                for n in ast.walk(node)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            }
            assert "build_core_storyboard" not in called
            assert not any(name.startswith("_pick") for name in called)
            body_names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            assert "CAMERA_LADDER" not in body_names
            assert "CONTINUITY_LIGHTING" not in body_names
            assert "ARC_BY_FORMAT" not in body_names
            return
    raise AssertionError("build_core_storyboard is not defined")


def test_the_endpoint_is_documented_under_the_core_tag(client):
    spec = client.get("/openapi.json").json()["paths"]["/api/v1/core/storyboard"]["post"]
    assert spec["tags"] == ["core"]
    assert spec["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("CoreStoryboardResponse")


# ---------------------------------------------------------------------------
# The pre-existing endpoint must not have moved
# ---------------------------------------------------------------------------


def test_the_legacy_expand_route_still_returns_its_four_fields(client):
    response = client.post("/api/v1/storyboards/expand", json={"brief": BRIEF, "scene_count": 4})
    assert response.status_code == 200
    scenes = response.json()["scenes"]
    assert len(scenes) == 4
    for scene in scenes:
        assert set(scene) == {"number", "title", "prompt", "duration_seconds"}


def test_the_legacy_expand_route_still_produces_prompt_text(client):
    """The two endpoints do different jobs: that one prompts, this one casts."""

    scene = client.post(
        "/api/v1/storyboards/expand", json={"brief": BRIEF, "scene_count": 3}
    ).json()["scenes"][0]
    assert "cinematic" in scene["prompt"]
    assert "SH" not in scene["prompt"]


def test_the_new_endpoint_does_not_produce_prompt_text(client):
    body = client.post("/api/v1/core/storyboard", json={"brief": BRIEF, "scene_count": 3}).json()
    assert "prompt" not in body
    assert not any("prompt" in shot for shot in body["shots"])
    assert "cinematic composition" not in body["beat_sheet"]
