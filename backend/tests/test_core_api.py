"""BROBOND CORE at the API boundary.

Two obligations are tested here:
  1. the new `/api/v1/core/*` endpoints expose the Core;
  2. every pre-existing contract still behaves exactly as before.
"""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ------------------------------------------------------------------- /core/direct


def test_direct_turns_a_plain_intention_into_a_brief() -> None:
    response = client.post("/api/v1/core/direct", json={"intent": "Quero vender uma camiseta"})
    assert response.status_code == 200
    body = response.json()
    assert body["format"] == "commercial"
    assert body["concept"] and body["script"] and body["logline"]
    assert body["music"] and body["pacing"]
    assert body["duration_seconds"] > 0
    assert 4 <= body["scene_count"] <= 8


def test_direct_returns_no_technical_prompt() -> None:
    body = client.post("/api/v1/core/direct", json={"intent": "Quero vender uma camiseta"}).json()
    assert "prompt" not in body
    for beat in body["beats"]:
        assert set(beat) == {
            "number",
            "objective",
            "emotion",
            "camera",
            "lighting",
            "motion",
            "duration_seconds",
            "shot_code",
            "reference",
        }


def test_direct_asks_one_short_question_when_the_intention_is_ambiguous() -> None:
    body = client.post("/api/v1/core/direct", json={"intent": "algo legal"}).json()
    assert body["clarification"]
    assert len(body["clarification"]) < 200


def test_direct_accepts_an_english_intention() -> None:
    body = client.post("/api/v1/core/direct", json={"intent": "product commercial for shoes"}).json()
    assert body["format"] == "commercial"
    assert body["beats"][0]["objective"].startswith("Establish")


def test_direct_rejects_an_empty_intention() -> None:
    assert client.post("/api/v1/core/direct", json={"intent": ""}).status_code == 422


# ------------------------------------------------------------------ /core/compile


def test_compile_returns_a_full_generation_spec() -> None:
    response = client.post(
        "/api/v1/core/compile",
        json={
            "prompt": "hero product shot of a black t-shirt on concrete",
            "persona_id": "CHAR_PETRICK",
            "style": "john-wick",
            "shot": "SH122",
            "project_id": "project-1",
        },
    )
    assert response.status_code == 200
    body = response.json()
    for field in (
        "project_id", "user_id", "persona_id", "style_id", "prompt_original", "prompt_compiled",
        "negative_prompt", "camera", "lens", "lighting", "motion", "weather", "aspect_ratio",
        "fps", "duration", "provider", "seed", "lora", "controlnet",
    ):
        assert field in body, f"spec response is missing {field}"
    assert body["style_id"] == "john-wick"
    assert body["persona_id"] == "CHAR_PETRICK"
    assert body["schema_version"] == "1.0"


def test_compile_applies_persona_memory_to_the_prompt() -> None:
    body = client.post(
        "/api/v1/core/compile", json={"prompt": "a portrait", "persona_id": "CHAR_PETRICK"}
    ).json()
    assert "Petrick Martins" in body["prompt_compiled"]
    assert body["prompt_original"] == "a portrait"


def test_compile_never_returns_the_raw_prompt_as_the_compiled_prompt() -> None:
    body = client.post("/api/v1/core/compile", json={"prompt": "a red car"}).json()
    assert body["prompt_compiled"] != "a red car"


def test_compile_exposes_the_resolution_trace() -> None:
    body = client.post(
        "/api/v1/core/compile", json={"prompt": "x", "style": "john-wick", "shot": "SH001"}
    ).json()
    assert body["trace"]["style_id"] == "john-wick"
    assert body["trace"]["shot_code"] == "SH001"
    assert body["trace"]["sources"]["lens"] == "shot"


def _token() -> dict:
    from uuid import uuid4

    return {
        "Authorization": f"Bearer {client.post('/api/v1/auth/register', json={'email': f'core-{uuid4()}@example.com', 'name': 'Core User', 'password': 'strong-pass-123'}).json()['access_token']}"
    }


def test_compile_is_a_dry_run_and_creates_no_job() -> None:
    # PR002: the queue is tenant-scoped and answers only to a token.
    headers = _token()
    queue_before = len(client.get("/api/v1/queue", headers=headers).json())
    client.post("/api/v1/core/compile", json={"prompt": "x"})
    assert len(client.get("/api/v1/queue", headers=headers).json()) == queue_before


def test_compile_binds_the_workspace_of_an_authenticated_caller() -> None:
    from uuid import uuid4

    token = client.post(
        "/api/v1/auth/register",
        json={"email": f"core-{uuid4()}@example.com", "name": "Core User", "password": "strong-pass-123"},
    ).json()["access_token"]
    body = client.post(
        "/api/v1/core/compile",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": "x"},
    ).json()
    assert body["user_id"], "an authenticated compile must carry the workspace"


def test_compile_validates_its_input() -> None:
    assert client.post("/api/v1/core/compile", json={"prompt": ""}).status_code == 422
    assert client.post("/api/v1/core/compile", json={"prompt": "x", "aspect_ratio": "7:3"}).status_code == 422
    assert client.post("/api/v1/core/compile", json={"prompt": "x", "duration": 999}).status_code == 422
    assert client.post("/api/v1/core/compile", json={"prompt": "x", "kind": "audio"}).status_code == 422


# ------------------------------------------------------- preserved pre-Core routes


def test_storyboard_contract_is_unchanged() -> None:
    response = client.post(
        "/api/v1/storyboards/expand",
        json={"brief": "A man walking through a future city", "scene_count": 4},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["scenes"]) == 4
    assert "cinematic" in body["scenes"][0]["prompt"]
    assert "wide establishing shot" in body["scenes"][0]["prompt"]
    assert body["scenes"][0]["title"] == "Scene 01"
    assert body["scenes"][0]["duration_seconds"] == 5


def test_storyboard_honours_scene_count() -> None:
    for count in (2, 3, 7, 12):
        body = client.post(
            "/api/v1/storyboards/expand", json={"brief": "a brief", "scene_count": count}
        ).json()
        assert len(body["scenes"]) == count


def test_storyboard_scenes_are_independently_renderable() -> None:
    body = client.post(
        "/api/v1/storyboards/expand", json={"brief": "a brief", "scene_count": 4}
    ).json()
    prompts = [scene["prompt"] for scene in body["scenes"]]
    assert len(set(prompts)) == 4, "each scene must compile to its own prompt"


def test_prompt_enhance_contract_is_unchanged() -> None:
    body = client.post(
        "/api/v1/prompts/enhance", json={"prompt": "A man walking", "persona": "a Brazilian athletic man"}
    ).json()
    assert body["original"] == "A man walking"
    assert "cinematic composition" in body["enhanced"]
    assert len(body["tokens"]) > 3


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/health",
        "/api/v1/system/gpu",
        "/api/v1/system/readiness",
        "/api/v1/system/media",
        "/api/v1/models/image",
        "/api/v1/models/video",
        "/api/v1/models/conditioning",
    ],
)
def test_existing_read_endpoints_still_answer(path: str) -> None:
    assert client.get(path).status_code == 200


def test_knowledge_requires_authentication() -> None:
    """PR002: the knowledge base holds persona PII, so it is no longer public.

    It still answers — to a token. (The seed content is global, shared by every
    authenticated tenant; there is deliberately no workspace filter.)
    """
    assert client.get("/api/v1/knowledge").status_code == 401
    response = client.get("/api/v1/knowledge", headers=_token(), params={"category": "character"})
    assert response.status_code == 200
    assert any(entry["code"] == "CHAR_PETRICK" for entry in response.json())


def test_compile_exposes_every_field_the_spec_carries() -> None:
    """Regression: Pydantic silently dropped the sampling extras, so a dry run
    hid exactly the values a provider would be handed."""

    import dataclasses

    from app.core.contracts import GenerationSpec

    body = client.post("/api/v1/core/compile", json={"prompt": "x"}).json()
    missing = {f.name for f in dataclasses.fields(GenerationSpec)} - set(body)
    assert not missing, f"spec fields hidden by the API response: {sorted(missing)}"


def test_compile_accepts_sampling_extras() -> None:
    body = client.post(
        "/api/v1/core/compile",
        json={"prompt": "x", "resolution": "4096", "steps": 50, "guidance_scale": 12, "native_audio": True},
    ).json()
    assert body["resolution"] == 4096
    assert body["steps"] == 50
    assert body["guidance_scale"] == 12
    assert body["native_audio"] is True


def test_compile_validates_sampling_extras() -> None:
    assert client.post("/api/v1/core/compile", json={"prompt": "x", "resolution": "9999"}).status_code == 422
    assert client.post("/api/v1/core/compile", json={"prompt": "x", "steps": 999}).status_code == 422
    assert client.post("/api/v1/core/compile", json={"prompt": "x", "guidance_scale": 99}).status_code == 422


def test_route_inventory_only_grew() -> None:
    from fastapi.routing import APIRoute, APIWebSocketRoute

    http = [route for route in app.routes if isinstance(route, APIRoute)]
    websockets = [route for route in app.routes if isinstance(route, APIWebSocketRoute)]
    assert len(websockets) == 2
    # 27 /api/v1 routes before the Core, 29 after ETAPA 2, 37 after ETAPA 4,
    # 46 after ETAPA 5, 50 after ETAPA 6, 51 after ETAPA 8, 52 after ETAPA 9,
    # 54 after ETAPA 10, 56 after ETAPA 13, 58 after ETAPA 14, 64 after PR003,
    # 65 after PR005 (Director AI production-plan route), 66 after PR007
    # (`/api/v1/providers`). The guard is that the number only grows: nothing
    # was ever removed.
    assert len([route for route in http if route.path.startswith("/api/v1")]) == 66


# ------------------------------------------------- no generation logic in routes


def test_no_route_contains_prompt_or_direction_logic() -> None:
    """ETAPA 2 rule: routes delegate, they never compose."""

    import app.main as main_module

    source = Path(main_module.__file__).read_text(encoding="utf-8")
    route_section = source.split("# BROBOND CORE", 1)[-1]

    forbidden = {
        "camera_progression": "camera ladder must live in DirectorAgent",
        "Ultra-realistic": "prompt wording must live in PromptCompiler",
        "IMAX quality": "the quality signature must live in PromptCompiler",
        "wide establishing shot": "camera language must live in DirectorAgent",
        "consistent blue-hour": "continuity lighting must live in DirectorAgent",
        "plastic skin": "the negative guard must live in PromptCompiler",
    }
    hits = {token: reason for token, reason in forbidden.items() if token in route_section}
    assert not hits, f"route layer still contains Core logic: {hits}"


def test_routes_only_call_into_the_core() -> None:
    import app.main as main_module

    source = Path(main_module.__file__).read_text(encoding="utf-8")
    assert "director_agent.expand(" in source
    assert "director_agent.direct(" in source
    assert "spec_builder.build_traced(" in source
    assert "prompt_engine.compose_scene_prompt(" in source


def test_the_core_components_are_wired_once_at_the_boundary() -> None:
    import app.main as main_module

    for name in (
        "memory_resolver",
        "style_resolver",
        "shot_resolver",
        "prompt_compiler",
        "director_agent",
        "spec_builder",
    ):
        assert hasattr(main_module, name), f"{name} is not wired in the application boundary"
    # The builder receives its collaborators instead of constructing them.
    assert main_module.spec_builder.memory is main_module.memory_resolver
    assert main_module.spec_builder.styles is main_module.style_resolver
    assert main_module.spec_builder.shots is main_module.shot_resolver
    assert main_module.spec_builder.compiler is main_module.prompt_compiler


def test_openapi_documents_the_core_tag() -> None:
    spec = client.get("/openapi.json").json()
    core_paths = [path for path in spec["paths"] if path.startswith("/api/v1/core/")]
    assert sorted(core_paths) == [
        "/api/v1/core/cinematic/audit",
        "/api/v1/core/cinematic/consistency",
        "/api/v1/core/cinematic/explain",
        "/api/v1/core/cinematic/framing",
        "/api/v1/core/cinematic/lenses",
        "/api/v1/core/cinematic/lenses/for",
        "/api/v1/core/cinematic/lighting",
        "/api/v1/core/cinematic/motivations",
        "/api/v1/core/cinematic/motivations/of",
        "/api/v1/core/compile",
        "/api/v1/core/direct",
        "/api/v1/core/director/production-plan",
        "/api/v1/core/personas",
        "/api/v1/core/personas/{persona_id}",
        "/api/v1/core/personas/{persona_id}/approve",
        "/api/v1/core/personas/{persona_id}/continuity",
        "/api/v1/core/personas/{persona_id}/episodes/{episode_id}/memory",
        "/api/v1/core/personas/{persona_id}/episodes/{episode_id}/snapshot",
        "/api/v1/core/personas/{persona_id}/retire",
        "/api/v1/core/personas/{persona_id}/revise",
        "/api/v1/core/providers",
        "/api/v1/core/providers/health",
        "/api/v1/core/quality/assess",
        "/api/v1/core/quality/rules",
        "/api/v1/core/shots",
        "/api/v1/core/shots/audit",
        "/api/v1/core/shots/families",
        "/api/v1/core/shots/{shot_code}",
        "/api/v1/core/storyboard",
        "/api/v1/core/storyboard/compile",
        "/api/v1/core/timeline",
        "/api/v1/core/timeline/formats",
    ]
    assert "GenerationSpecResponse" in spec["components"]["schemas"]
    assert "DirectorBriefResponse" in spec["components"]["schemas"]
    assert "DirectorProductionPlanResponse" in spec["components"]["schemas"]


def test_compiled_prompt_shape_is_stable_across_calls() -> None:
    first = client.post("/api/v1/core/compile", json={"prompt": "x", "style": "john-wick"}).json()
    second = client.post("/api/v1/core/compile", json={"prompt": "x", "style": "john-wick"}).json()
    assert first["prompt_compiled"] == second["prompt_compiled"]
    assert first["spec_id"] != second["spec_id"]
    assert re.fullmatch(r"[0-9a-f]{32}", first["spec_id"])
