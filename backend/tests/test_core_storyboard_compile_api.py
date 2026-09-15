"""ETAPA 9 tests — the storyboard compile endpoint.

`POST /api/v1/core/storyboard/compile` casts a brief (ETAPA 8) and compiles one
prompt per scene (ETAPA 9). The route only wires two Core components together.
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


def _compile(client: TestClient, **overrides) -> dict:
    payload = {"brief": BRIEF, "scene_count": 3, **overrides}
    response = client.post("/api/v1/core/storyboard/compile", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# The compiled output
# ---------------------------------------------------------------------------


def test_a_brief_comes_back_as_one_prompt_per_scene(client):
    body = _compile(client)
    assert body["scene_count"] == 3
    assert len(body["scenes"]) == 3
    assert body["shot_codes"] == ["SH002", "SH028", "SH253"]
    assert [scene["shot_code"] for scene in body["scenes"]] == body["shot_codes"]


def test_a_scene_prompt_carries_the_cast_shot_not_a_placeholder(client):
    scene = _compile(client)["scenes"][0]
    assert "slow crane reveal descending to street level" in scene["prompt"]
    assert "24mm" in scene["prompt"]
    assert "blue hour ambience" in scene["prompt"]
    assert "motivated by the beat" not in scene["prompt"]


def test_no_scene_prompt_repeats_a_clause(client):
    for scene in _compile(client)["scenes"]:
        clauses = [part.strip().casefold() for part in scene["prompt"].split(", ")]
        assert len(clauses) == len(set(clauses)), scene["shot_code"]


def test_the_colour_grade_lands_in_its_own_block(client):
    scene = _compile(client, style="neo-tokyo")["scenes"][0]
    assert "cyan-magenta" in scene["prompt"]
    assert "neo tokyo" in scene["prompt"]
    # STYLE sits after MOTION; COLOR sits after LIGHT.
    assert scene["prompt"].index("cyan-magenta") < scene["prompt"].index("neo tokyo")


def test_an_approved_persona_reaches_the_prompt(client):
    scene = _compile(client, persona_id="CHAR_PETRICK")["scenes"][0]
    assert "Petrick Martins" in scene["prompt"]


def test_a_planned_persona_never_leaks_into_a_prompt(client):
    """CHAR_JEFFERSON is PLANNED, so identity must not reach the model."""

    body = _compile(client, persona_id="CHAR_JEFFERSON")
    assert all("Jefferson" not in scene["prompt"] for scene in body["scenes"])


def test_an_unknown_persona_is_ignored_rather_than_invented(client):
    body = _compile(client, persona_id="CHAR_NOBODY")
    assert body["scene_count"] == 3
    assert all(scene["prompt"] for scene in body["scenes"])


def test_the_brobond_negative_guard_is_always_present(client):
    scene = _compile(client)["scenes"][0]
    assert "plastic skin" in scene["negative_prompt"]
    assert "generic ai look" in scene["negative_prompt"]


def test_a_caller_negative_prompt_is_prepended_to_the_guard(client):
    scene = _compile(client, negative_prompt="extra limbs")["scenes"][0]
    assert scene["negative_prompt"].startswith("extra limbs")
    assert "plastic skin" in scene["negative_prompt"]


def test_the_negative_prompt_never_leaks_into_the_prompt(client):
    scene = _compile(client, negative_prompt="watermark")["scenes"][0]
    assert "watermark" not in scene["prompt"]


# ---------------------------------------------------------------------------
# Budget and trimming are visible, never silent
# ---------------------------------------------------------------------------


def test_the_applied_budget_is_reported(client):
    assert _compile(client, provider="flux-dev")["budget"] == 1000
    assert _compile(client, provider="wan-video")["budget"] == 1200


def test_every_scene_respects_the_budget_of_its_provider(client):
    body = _compile(client, provider="flux-dev", scene_count=12)
    assert all(len(scene["prompt"]) <= body["budget"] for scene in body["scenes"])


def test_a_trimmed_scene_says_what_it_dropped(client):
    body = _compile(client, scene_count=12, provider="flux-dev")
    dropped = [clause for scene in body["scenes"] for clause in scene["dropped"]]
    assert all(name in {"continuity", "environment", "motion", "lens", "light",
                        "camera", "style", "action", "output", "color"} for name in dropped)


def test_tokens_are_returned_for_each_scene(client):
    scene = _compile(client)["scenes"][0]
    assert scene["tokens"]
    assert ", ".join(scene["tokens"]) == scene["prompt"]


# ---------------------------------------------------------------------------
# Validation still travels with the compiled output
# ---------------------------------------------------------------------------


def test_an_invalid_sequence_is_still_reported_next_to_its_prompts(client):
    body = _compile(client, scene_count=12, duration_per_scene=30.0)
    assert body["valid"] is False
    assert "runtime" in {finding["rule"] for finding in body["violations"]}
    assert len(body["scenes"]) == 12, "the prompts are still returned; a director decides"


def test_a_valid_sequence_reports_no_violations(client):
    body = _compile(client)
    assert body["valid"] is True
    assert body["violations"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"brief": ""},
        {"brief": "x", "scene_count": 1},
        {"brief": "x", "scene_count": 40},
        {"brief": "x", "duration_per_scene": 0},
    ],
)
def test_out_of_range_requests_are_refused(client, payload):
    assert client.post("/api/v1/core/storyboard/compile", json=payload).status_code == 422


def test_a_missing_brief_is_refused(client):
    assert client.post("/api/v1/core/storyboard/compile", json={}).status_code == 422


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------


def test_the_route_contains_no_composition_logic_of_its_own():
    """It wires two Core components; it does not build blocks itself."""

    source = pathlib.Path("backend/app/main.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "compile_core_storyboard":
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            assert "PROMPT_BLOCK_ORDER" not in names
            assert "PromptBlocks" not in names
            assert "DROP_PRIORITY" not in names
            assert "ARC_BY_FORMAT" not in names
            assert "output_block" not in names
            return
    raise AssertionError("compile_core_storyboard is not defined")


def test_the_endpoint_is_documented_under_the_core_tag(client):
    spec = client.get("/openapi.json").json()["paths"]["/api/v1/core/storyboard/compile"]["post"]
    assert spec["tags"] == ["core"]
    assert spec["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("CoreStoryboardCompileResponse")


def test_the_casting_endpoint_is_untouched(client):
    """ETAPA 8's endpoint still casts without compiling."""

    body = client.post("/api/v1/core/storyboard", json={"brief": BRIEF, "scene_count": 3}).json()
    assert "scenes" not in body
    assert "beat_sheet" in body
    assert "prompt" not in body
