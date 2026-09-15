"""ETAPA 4 — the persona memory HTTP surface.

`persona_engine` is a module-level singleton, so every test here runs against a
fresh ledger injected over it. Writes never reach the shared ledger, which is
what keeps `test_core_api.py` (and the spec builder) unaffected by this file.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.memory_resolver import MemoryResolver
from app.core.persona_memory import PersonaLedger
from app.main import app

client = TestClient(app)

# PR002: the persona memory routes are protected; one tenant answers for all
# the tests in this file (the ledger they touch is isolated per test).
from uuid import uuid4  # noqa: E402

_REGISTER = client.post(
    "/api/v1/auth/register",
    json={"email": f"core-persona-{uuid4()}@example.com", "name": "Core Persona API", "password": "strong-pass-123"},
)
assert _REGISTER.status_code == 201, _REGISTER.text
HEADERS = {"Authorization": f"Bearer {_REGISTER.json()['access_token']}"}


@pytest.fixture(autouse=True)
def isolated_persona_memory(monkeypatch):
    """Point the engine and the resolver at a throwaway ledger for one test."""

    from app import main

    ledger = PersonaLedger()
    monkeypatch.setattr(main.persona_engine, "ledger", ledger)
    monkeypatch.setattr(main.persona_engine, "memory", MemoryResolver(ledger))
    monkeypatch.setattr(main.memory_resolver, "_source", ledger)
    yield


def test_the_library_lists_both_canonical_characters() -> None:
    body = client.get("/api/v1/core/personas", headers=HEADERS).json()
    assert {entry["persona_id"]: entry for entry in body}["CHAR_PETRICK"]["generable"] is True
    jefferson = {entry["persona_id"]: entry for entry in body}["CHAR_JEFFERSON"]
    assert jefferson["status"] == "planned"
    assert jefferson["generable"] is False
    assert jefferson["identity_phrase"] == "", "an undefined identity must not produce a prompt block"


def test_the_library_can_be_filtered() -> None:
    assert len(client.get("/api/v1/core/personas", headers=HEADERS, params={"query": "petrick"}).json()) == 1


def test_an_unknown_persona_is_404() -> None:
    assert client.get("/api/v1/core/personas/CHAR_NOBODY", headers=HEADERS).status_code == 404
    assert client.post(
        "/api/v1/core/personas/CHAR_NOBODY/revise", headers=HEADERS, json={"actor": "x", "reason": "y", "hair": "z"}
    ).status_code == 404
    assert client.post("/api/v1/core/personas/CHAR_NOBODY/approve", headers=HEADERS, json={"actor": "x"}).status_code == 404


def test_an_identity_change_without_authorization_is_409() -> None:
    response = client.post(
        "/api/v1/core/personas/CHAR_PETRICK/revise", headers=HEADERS,
        json={"actor": "estagiario", "reason": "achei melhor", "eyes": "green eyes"},
    )
    assert response.status_code == 409
    assert "authorization" in response.json()["detail"]


def test_an_authorized_identity_change_is_recorded() -> None:
    response = client.post(
        "/api/v1/core/personas/CHAR_PETRICK/revise", headers=HEADERS,
        json={"actor": "diretor", "reason": "novo arco em EP2", "authorized": True, "eyes": "green eyes"},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["revision"], body["version"], body["action"], body["changed"]) == (2, 2, "revised", ["eyes"])
    assert body["actor"] == "diretor"
    assert body["reason"] == "novo arco em EP2"


def test_a_revision_without_any_field_is_422_not_a_silent_noop() -> None:
    response = client.post(
        "/api/v1/core/personas/CHAR_PETRICK/revise", headers=HEADERS, json={"actor": "diretor", "reason": "nada", "authorized": True}
    )
    assert response.status_code == 409
    assert "changes nothing" in response.json()["detail"]


def test_revision_fields_are_validated() -> None:
    assert (
        client.post(
            "/api/v1/core/personas/CHAR_PETRICK/revise", headers=HEADERS,
            json={"actor": "x", "reason": "y", "authorized": True, "age": 500},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/core/personas/CHAR_PETRICK/revise", headers=HEADERS,
            json={"actor": "x", "reason": "y", "authorized": True, "height_m": 0.1},
        ).status_code
        == 422
    )


def test_actor_and_reason_are_mandatory_on_every_write() -> None:
    assert (
        client.post(
            "/api/v1/core/personas/CHAR_PETRICK/revise", headers=HEADERS, json={"reason": "sem autor", "hair": "shaved"}
        ).status_code
        == 422
    )
    assert client.post("/api/v1/core/personas/CHAR_PETRICK/approve", headers=HEADERS, json={"reason": "sem autor"}).status_code == 422


def test_history_grows_and_is_attributed() -> None:
    client.post(
        "/api/v1/core/personas/CHAR_PETRICK/revise", headers=HEADERS,
        json={"actor": "diretor", "reason": "ep2", "authorized": True, "eyes": "green eyes"},
    )
    client.post(
        "/api/v1/core/personas/CHAR_PETRICK/revise", headers=HEADERS,
        json={"actor": "ml", "reason": "publicado", "lora_path": "weights/v2.safetensors"},
    )
    body = client.get("/api/v1/core/personas/CHAR_PETRICK", headers=HEADERS).json()
    assert [(entry["revision"], entry["version"], entry["action"]) for entry in body["history"]] == [
        (1, 1, "registered"),
        (2, 2, "revised"),
        (3, 2, "updated"),
    ]
    assert body["identity_versions"] == [1, 2]
    assert body["changed_fields"] == {"eyes": [2]}
    assert body["identity_changed"] is True


def test_an_administrative_edit_does_not_bump_the_identity_version() -> None:
    client.post(
        "/api/v1/core/personas/CHAR_PETRICK/revise", headers=HEADERS,
        json={"actor": "ml", "reason": "publicado", "lora_path": "weights/v2.safetensors"},
    )
    body = client.get("/api/v1/core/personas/CHAR_PETRICK", headers=HEADERS).json()
    assert body["version"] == 1
    assert body["persona"]["lora_path"] == "weights/v2.safetensors"


def test_approval_is_refused_for_an_undefined_identity() -> None:
    response = client.post("/api/v1/core/personas/CHAR_JEFFERSON/approve", headers=HEADERS, json={"actor": "cto"})
    assert response.status_code == 409
    assert "approval requires definition" in response.json()["detail"]
    assert client.get("/api/v1/core/personas", headers=HEADERS, params={"query": "jefferson"}).json()[0]["generable"] is False


def test_a_full_lifecycle_over_http() -> None:
    """Define -> approve -> generate-eligible, all attributed."""

    from app.main import persona_engine

    persona_engine.create(persona_id="CHAR_NOVA", name="Nova", actor="produtor")
    assert client.get("/api/v1/core/personas/CHAR_NOVA", headers=HEADERS).json()["generable"] is False

    client.post(
        "/api/v1/core/personas/CHAR_NOVA/revise", headers=HEADERS,
        json={"actor": "diretor", "reason": "identidade", "authorized": True, "age": 32, "eyes": "amber eyes"},
    )
    approved = client.post("/api/v1/core/personas/CHAR_NOVA/approve", headers=HEADERS, json={"actor": "cto", "reason": "EP1"})
    assert approved.status_code == 200
    assert approved.json()["generable"] is True
    assert "Nova" in approved.json()["identity_phrase"]

    retired = client.post("/api/v1/core/personas/CHAR_NOVA/retire", headers=HEADERS, json={"actor": "produtor", "reason": "fim"})
    assert retired.json()["generable"] is False
    assert client.post("/api/v1/core/personas/CHAR_NOVA/retire", headers=HEADERS, json={"actor": "produtor"}).status_code == 409


def test_an_episode_snapshot_survives_later_revisions() -> None:
    client.post("/api/v1/core/personas/CHAR_PETRICK/episodes/EP01/snapshot", headers=HEADERS)
    client.post(
        "/api/v1/core/personas/CHAR_PETRICK/revise", headers=HEADERS,
        json={"actor": "diretor", "reason": "novo look", "authorized": True, "eyes": "green eyes"},
    )
    client.post("/api/v1/core/personas/CHAR_PETRICK/episodes/EP02/snapshot", headers=HEADERS)

    assert client.get("/api/v1/core/personas/CHAR_PETRICK/episodes/EP01/memory", headers=HEADERS).json()["persona"]["eyes"] == (
        "dark brown eyes"
    )
    assert client.get("/api/v1/core/personas/CHAR_PETRICK/episodes/EP02/memory", headers=HEADERS).json()["persona"]["eyes"] == (
        "green eyes"
    )
    assert client.get("/api/v1/core/personas/CHAR_PETRICK", headers=HEADERS).json()["persona"]["eyes"] == "green eyes"


def test_snapshot_payload_carries_the_version_it_was_taken_at() -> None:
    body = client.post("/api/v1/core/personas/CHAR_PETRICK/episodes/EP01/snapshot", headers=HEADERS).json()
    assert body["snapshot_of_version"] == 1
    assert body["persona_id"] == "CHAR_PETRICK"


def test_recall_without_a_snapshot_is_404_not_a_guess() -> None:
    response = client.get("/api/v1/core/personas/CHAR_PETRICK/episodes/EP99/memory", headers=HEADERS)
    assert response.status_code == 404
    assert "no memory snapshot" in response.json()["detail"]


def test_continuity_reports_drift() -> None:
    client.post("/api/v1/core/personas/CHAR_PETRICK/episodes/EP01/snapshot", headers=HEADERS)
    client.post(
        "/api/v1/core/personas/CHAR_PETRICK/revise", headers=HEADERS,
        json={"actor": "diretor", "reason": "novo look", "authorized": True, "eyes": "green eyes"},
    )
    client.post("/api/v1/core/personas/CHAR_PETRICK/episodes/EP02/snapshot", headers=HEADERS)

    body = client.get(
        "/api/v1/core/personas/CHAR_PETRICK/continuity", headers=HEADERS, params={"episodes": ["EP01", "EP02"]}
    ).json()
    assert body["consistent"] is False
    assert body["distinct_identities"] == 2


def test_continuity_with_no_episodes_is_consistent_and_empty() -> None:
    body = client.get("/api/v1/core/personas/CHAR_PETRICK/continuity", headers=HEADERS).json()
    assert body["consistent"] is True
    assert body["episodes_without_snapshot"] == []


def test_an_undefined_identity_never_leaks_into_a_compiled_prompt() -> None:
    """End to end: the persona API and the spec builder share one ledger."""

    spec = client.post("/api/v1/core/compile", json={"prompt": "a portrait", "persona_id": "CHAR_JEFFERSON"}).json()
    assert spec["persona_id"] is None
    assert "Jefferson" not in spec["prompt_compiled"]


def test_a_newly_approved_persona_reaches_the_compiler() -> None:
    from app.main import persona_engine

    persona_engine.create(persona_id="CHAR_NOVA", name="Nova", actor="produtor")
    persona_engine.revise(
        "CHAR_NOVA", actor="diretor", reason="identidade", authorized=True, age=32, eyes="amber eyes"
    )
    persona_engine.approve("CHAR_NOVA", actor="cto")

    spec = client.post("/api/v1/core/compile", json={"prompt": "a portrait", "persona_id": "CHAR_NOVA"}).json()
    assert spec["persona_id"] == "CHAR_NOVA"
    assert "Nova" in spec["prompt_compiled"]


def test_the_persona_routes_contain_no_identity_logic() -> None:
    """Routes translate HTTP and map errors; the rules live in the Core."""

    import inspect

    import app.main as main_module

    source = inspect.getsource(main_module)
    for name in (
        "list_persona_memory",
        "read_persona_memory",
        "revise_persona_memory",
        "approve_persona_memory",
        "retire_persona_memory",
        "snapshot_persona_for_episode",
        "recall_episode_memory",
        "persona_continuity",
    ):
        body = inspect.getsource(getattr(main_module, name))
        for forbidden in ("PERSONA_IDENTITY_FIELDS", "status is PersonaStatus", "version + 1", "_is_defined"):
            assert forbidden not in body, f"{name} decides identity rules inline ({forbidden})"


def test_the_openapi_surface_documents_the_new_endpoints() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/v1/core/personas",
        "/api/v1/core/personas/{persona_id}",
        "/api/v1/core/personas/{persona_id}/revise",
        "/api/v1/core/personas/{persona_id}/approve",
        "/api/v1/core/personas/{persona_id}/retire",
        "/api/v1/core/personas/{persona_id}/episodes/{episode_id}/snapshot",
        "/api/v1/core/personas/{persona_id}/episodes/{episode_id}/memory",
        "/api/v1/core/personas/{persona_id}/continuity",
    ):
        assert path in paths, path
