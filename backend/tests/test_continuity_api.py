"""V3.2 — the thirteen continuity routes: locks, resolver, episodes.

End to end over HTTP: every test registers a fresh user (hence a fresh
workspace), so workspaces isolate tenants the way production does. The suite
pins status codes (200/201/401/404/409/422), the audit rows each mutation
writes, the episode-override fallback through the wire, the resolver's
consistent/missing signals, and the frozen episode snapshots.
"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete as sa_delete, select

from app.db import SessionLocal
from app.main import app
from app.models import AuditLog, User, Workspace

client = TestClient(app)


def _register(tag: str = "continuity") -> tuple[str, dict[str, str]]:
    email = f"{tag}-{uuid.uuid4()}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "name": "Continuity Test", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return email, {"Authorization": f"Bearer {token}"}


def _persona() -> str:
    return f"CHAR_{uuid.uuid4().hex[:8].upper()}"


def _latest(action: str) -> AuditLog | None:
    with SessionLocal() as db:
        return db.scalar(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.created_at.desc())
        )


def _lock_all(headers: dict[str, str], persona: str, campaign: str = "legacy") -> None:
    assert client.put("/api/v1/continuity/identity", json={"persona_id": persona, "face": "oval face"}, headers=headers).status_code == 200
    assert client.put("/api/v1/continuity/wardrobe", json={"persona_id": persona, "campaign_id": campaign, "outfit": "black blazer"}, headers=headers).status_code == 200
    assert client.put("/api/v1/continuity/location", json={"persona_id": persona, "campaign_id": campaign, "showroom": "Flagship"}, headers=headers).status_code == 200
    assert client.put("/api/v1/continuity/vehicle", json={"persona_id": persona, "campaign_id": campaign, "vehicle": "RAM 1500", "color": "black"}, headers=headers).status_code == 200
    assert client.put("/api/v1/continuity/voice", json={"persona_id": persona, "voice_profile": "v1"}, headers=headers).status_code == 200


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_identity_requires_a_token() -> None:
    assert client.put("/api/v1/continuity/identity", json={"persona_id": "X", "face": "f"}).status_code == 401
    assert client.get("/api/v1/continuity/identity/X").status_code == 401


def test_identity_lock_returns_the_frozen_shape_and_audits() -> None:
    _, headers = _register()
    persona = _persona()
    response = client.put(
        "/api/v1/continuity/identity",
        json={"persona_id": persona, "face": "oval face", "hair": "tied back"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "persona_id", "face", "hair", "beard", "body", "skin", "age_appearance",
        "fingerprint", "version", "updated_at",
    }
    assert (body["persona_id"], body["face"], body["hair"]) == (persona, "oval face", "tied back")
    assert len(body["fingerprint"]) == 16 and body["version"] == 1 and body["updated_at"]

    entry = _latest("continuity.identity.locked")
    assert entry is not None and entry.resource_type == "continuity_lock"
    assert json.loads(entry.detail or "{}")["fingerprint"] == body["fingerprint"]

    reread = client.get(f"/api/v1/continuity/identity/{persona}", headers=headers)
    assert reread.status_code == 200
    assert reread.json()["fingerprint"] == body["fingerprint"]


def test_identity_relock_bumps_the_version() -> None:
    _, headers = _register()
    persona = _persona()
    first = client.put("/api/v1/continuity/identity", json={"persona_id": persona, "face": "a"}, headers=headers).json()
    second = client.put("/api/v1/continuity/identity", json={"persona_id": persona, "face": "b"}, headers=headers).json()
    assert second["version"] == first["version"] + 1
    assert second["fingerprint"] != first["fingerprint"]


def test_identity_validates() -> None:
    _, headers = _register()
    assert client.put("/api/v1/continuity/identity", json={"persona_id": "", "face": "f"}, headers=headers).status_code == 422
    assert client.put("/api/v1/continuity/identity", json={"persona_id": "  ", "face": "f"}, headers=headers).status_code == 422
    assert client.put("/api/v1/continuity/identity", json={"persona_id": _persona()}, headers=headers).status_code == 422
    assert client.put("/api/v1/continuity/identity", json={"persona_id": _persona(), "face": 123}, headers=headers).status_code == 422


def test_identity_missing_and_foreign_read_as_404() -> None:
    _, headers = _register()
    assert client.get("/api/v1/continuity/identity/CHAR_NEVER", headers=headers).status_code == 404
    persona = _persona()
    client.put("/api/v1/continuity/identity", json={"persona_id": persona, "face": "f"}, headers=headers)
    _, other = _register(tag="continuity-other")
    assert client.get(f"/api/v1/continuity/identity/{persona}", headers=other).status_code == 404


# ---------------------------------------------------------------------------
# Wardrobe / location / vehicle (scoped locks share the same wire behaviour)
# ---------------------------------------------------------------------------


SCOPED = [
    ("wardrobe", {"outfit": "black blazer"}, "continuity.wardrobe.locked", {"outfit"}),
    ("location", {"showroom": "Flagship"}, "continuity.location.locked", {"showroom", "city"}),
    ("vehicle", {"vehicle": "RAM 1500", "color": "black"}, "continuity.vehicle.locked", {"vehicle", "color"}),
]


@pytest.mark.parametrize("lock_type,payload,action,fields", SCOPED)
def test_scoped_lock_round_trip_and_audit(lock_type: str, payload: dict, action: str, fields: set) -> None:
    _, headers = _register()
    persona = _persona()
    response = client.put(
        f"/api/v1/continuity/{lock_type}",
        json={"persona_id": persona, "campaign_id": "legacy", **payload},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["persona_id"] == persona and body["campaign_id"] == "legacy"
    assert body["source_episode"] is None  # written as the campaign default
    for name in fields:
        assert body[name] == payload.get(name, "")
    assert len(body["fingerprint"]) == 16 and body["version"] == 1

    entry = _latest(action)
    assert entry is not None and entry.workspace_id

    reread = client.get(
        f"/api/v1/continuity/{lock_type}",
        params={"persona_id": persona, "campaign_id": "legacy"},
        headers=headers,
    )
    assert reread.status_code == 200
    assert reread.json()["fingerprint"] == body["fingerprint"]


@pytest.mark.parametrize("lock_type,payload,action,fields", SCOPED)
def test_scoped_lock_requires_a_token(lock_type: str, payload: dict, action: str, fields: set) -> None:
    assert client.put(f"/api/v1/continuity/{lock_type}", json={"persona_id": "X", **payload}).status_code == 401
    assert client.get(f"/api/v1/continuity/{lock_type}", params={"persona_id": "X"}).status_code == 401


@pytest.mark.parametrize("lock_type,payload,action,fields", SCOPED)
def test_scoped_lock_episode_override_and_fallback(lock_type: str, payload: dict, action: str, fields: set) -> None:
    _, headers = _register()
    persona = _persona()
    base = {"persona_id": persona, "campaign_id": "legacy", **payload}
    assert client.put(f"/api/v1/continuity/{lock_type}", json=base, headers=headers).status_code == 200

    # Episode 3 inherits the campaign default…
    inherited = client.get(
        f"/api/v1/continuity/{lock_type}",
        params={"persona_id": persona, "campaign_id": "legacy", "episode": 3},
        headers=headers,
    )
    assert inherited.status_code == 200
    assert inherited.json()["source_episode"] is None

    # …until it carries its own override, which other episodes never see.
    override_payload = dict(payload)
    first_field = sorted(fields)[0]
    override_payload[first_field] = "episode-three-look"
    override = client.put(
        f"/api/v1/continuity/{lock_type}",
        json={**base, "episode": 3, **override_payload},
        headers=headers,
    )
    assert override.status_code == 200, override.text
    assert override.json()["source_episode"] == 3

    resolved = client.get(
        f"/api/v1/continuity/{lock_type}",
        params={"persona_id": persona, "campaign_id": "legacy", "episode": 3},
        headers=headers,
    )
    assert resolved.json()[first_field] == "episode-three-look"

    other = client.get(
        f"/api/v1/continuity/{lock_type}",
        params={"persona_id": persona, "campaign_id": "legacy", "episode": 4},
        headers=headers,
    )
    assert other.json()[first_field] == payload.get(first_field, "")


@pytest.mark.parametrize("lock_type,payload,action,fields", SCOPED)
def test_scoped_lock_missing_and_foreign_read_as_404(lock_type: str, payload: dict, action: str, fields: set) -> None:
    _, headers = _register()
    missing = client.get(
        f"/api/v1/continuity/{lock_type}",
        params={"persona_id": "CHAR_NEVER"},
        headers=headers,
    )
    assert missing.status_code == 404
    persona = _persona()
    client.put(f"/api/v1/continuity/{lock_type}", json={"persona_id": persona, **payload}, headers=headers)
    _, other = _register(tag="continuity-other")
    foreign = client.get(
        f"/api/v1/continuity/{lock_type}",
        params={"persona_id": persona},
        headers=other,
    )
    assert foreign.status_code == 404


def test_wardrobe_validates() -> None:
    _, headers = _register()
    persona = _persona()
    assert client.put("/api/v1/continuity/wardrobe", json={"persona_id": persona}, headers=headers).status_code == 422
    assert client.put("/api/v1/continuity/wardrobe", json={"persona_id": persona, "outfit": "x", "episode": 0}, headers=headers).status_code == 422
    bad = client.get("/api/v1/continuity/wardrobe", params={"persona_id": persona, "episode": 0}, headers=headers)
    assert bad.status_code == 422


def test_location_validates() -> None:
    _, headers = _register()
    persona = _persona()
    assert client.put("/api/v1/continuity/location", json={"persona_id": persona, "city": "Lisboa"}, headers=headers).status_code == 422


def test_vehicle_validates() -> None:
    _, headers = _register()
    persona = _persona()
    assert client.put("/api/v1/continuity/vehicle", json={"persona_id": persona, "vehicle": "RAM"}, headers=headers).status_code == 422
    assert client.put("/api/v1/continuity/vehicle", json={"persona_id": persona, "color": "black"}, headers=headers).status_code == 422


# ---------------------------------------------------------------------------
# Voice
# ---------------------------------------------------------------------------


def test_voice_requires_a_token() -> None:
    assert client.put("/api/v1/continuity/voice", json={"persona_id": "X", "voice_profile": "v"}).status_code == 401
    assert client.get("/api/v1/continuity/voice/X").status_code == 401


def test_voice_lock_round_trip_and_audit() -> None:
    _, headers = _register()
    persona = _persona()
    response = client.put(
        "/api/v1/continuity/voice",
        json={"persona_id": persona, "voice_profile": "petrick-low-warm", "default_emotion": "confident"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"persona_id", "voice_profile", "default_emotion", "speed", "intensity", "fingerprint", "version", "updated_at"}
    assert body["voice_profile"] == "petrick-low-warm"
    assert _latest("continuity.voice.locked") is not None

    reread = client.get(f"/api/v1/continuity/voice/{persona}", headers=headers)
    assert reread.status_code == 200
    assert reread.json()["fingerprint"] == body["fingerprint"]


def test_voice_validates_and_misses_as_404() -> None:
    _, headers = _register()
    assert client.put("/api/v1/continuity/voice", json={"persona_id": _persona()}, headers=headers).status_code == 422
    assert client.get("/api/v1/continuity/voice/CHAR_NEVER", headers=headers).status_code == 404
    persona = _persona()
    client.put("/api/v1/continuity/voice", json={"persona_id": persona, "voice_profile": "v"}, headers=headers)
    _, other = _register(tag="continuity-other")
    assert client.get(f"/api/v1/continuity/voice/{persona}", headers=other).status_code == 404


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


def test_resolve_requires_a_token() -> None:
    assert client.get("/api/v1/continuity/resolve", params={"persona_id": "X"}).status_code == 401


def test_resolve_empty_context_reports_everything_missing() -> None:
    _, headers = _register()
    response = client.get(
        "/api/v1/continuity/resolve",
        params={"persona_id": _persona(), "campaign_id": "legacy", "episode": 1},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["missing"] == ["identity", "wardrobe", "location", "vehicle", "voice"]
    assert body["phrases"] == [] and body["fingerprints"] == {} and body["block"] == ""
    assert body["consistent"] is False
    assert body["identity"] is None and body["voice"] is None


def test_resolve_full_context_is_consistent() -> None:
    _, headers = _register()
    persona = _persona()
    _lock_all(headers, persona)
    response = client.get(
        "/api/v1/continuity/resolve",
        params={"persona_id": persona, "campaign_id": "legacy", "episode": 1},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["missing"] == [] and body["drift"] == []
    assert body["consistent"] is True
    assert len(body["phrases"]) == 5
    assert set(body["fingerprints"]) == {"identity", "wardrobe", "location", "vehicle", "voice"}
    assert body["identity"]["face"] == "oval face"
    assert body["wardrobe"]["outfit"] == "black blazer"
    assert body["location"]["showroom"] == "Flagship"
    assert body["vehicle"]["vehicle"] == "RAM 1500"
    assert body["voice"]["voice_profile"] == "v1"
    assert body["block"].startswith("mesmo personagem")


def test_resolve_partial_context_lists_only_the_gaps() -> None:
    _, headers = _register()
    persona = _persona()
    client.put("/api/v1/continuity/identity", json={"persona_id": persona, "face": "f"}, headers=headers)
    body = client.get(
        "/api/v1/continuity/resolve",
        params={"persona_id": persona, "campaign_id": "legacy", "episode": 1},
        headers=headers,
    ).json()
    assert body["missing"] == ["wardrobe", "location", "vehicle", "voice"]
    assert len(body["phrases"]) == 1
    assert body["consistent"] is False


def test_resolve_defaults_and_validates() -> None:
    _, headers = _register()
    persona = _persona()
    defaulted = client.get("/api/v1/continuity/resolve", params={"persona_id": persona}, headers=headers)
    assert defaulted.status_code == 200
    assert (defaulted.json()["campaign_id"], defaulted.json()["episode"]) == ("default", 1)
    assert client.get("/api/v1/continuity/resolve", params={"persona_id": "  "}, headers=headers).status_code == 422
    assert client.get("/api/v1/continuity/resolve", params={"persona_id": persona, "episode": 0}, headers=headers).status_code == 422


# ---------------------------------------------------------------------------
# Episodes
# ---------------------------------------------------------------------------


def test_episodes_require_a_token() -> None:
    assert client.post("/api/v1/continuity/episodes", json={"persona_id": "X"}).status_code == 401
    assert client.get("/api/v1/continuity/episodes").status_code == 401


def test_create_episode_auto_numbers_and_freezes_the_snapshot() -> None:
    _, headers = _register()
    persona = _persona()
    _lock_all(headers, persona)
    first = client.post(
        "/api/v1/continuity/episodes",
        json={"persona_id": persona, "campaign_id": "legacy", "title": "Pilot"},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    body = first.json()
    assert set(body) == {"id", "workspace_id", "persona_id", "campaign_id", "episode", "title", "notes", "snapshot", "created_at"}
    assert (body["episode"], body["title"]) == (1, "Pilot")
    assert body["snapshot"]["consistent"] is True
    assert len(body["snapshot"]["phrases"]) == 5
    assert set(body["snapshot"]["locks"]) == {"identity", "wardrobe", "location", "vehicle", "voice"}

    entry = _latest("continuity.episode.created")
    assert entry is not None and entry.resource_type == "continuity_episode"

    second = client.post(
        "/api/v1/continuity/episodes",
        json={"persona_id": persona, "campaign_id": "legacy", "title": "Second"},
        headers=headers,
    )
    assert second.json()["episode"] == 2


def test_create_episode_accepts_explicit_numbers_and_conflicts() -> None:
    _, headers = _register()
    persona = _persona()
    created = client.post(
        "/api/v1/continuity/episodes",
        json={"persona_id": persona, "campaign_id": "legacy", "episode": 7, "title": "Seven", "notes": "night"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert (created.json()["episode"], created.json()["notes"]) == (7, "night")
    duplicate = client.post(
        "/api/v1/continuity/episodes",
        json={"persona_id": persona, "campaign_id": "legacy", "episode": 7},
        headers=headers,
    )
    assert duplicate.status_code == 409


def test_episode_snapshot_never_moves_after_a_relock() -> None:
    _, headers = _register()
    persona = _persona()
    _lock_all(headers, persona)
    created = client.post(
        "/api/v1/continuity/episodes",
        json={"persona_id": persona, "campaign_id": "legacy"},
        headers=headers,
    ).json()
    before = created["snapshot"]["fingerprints"]["wardrobe"]
    client.put(
        "/api/v1/continuity/wardrobe",
        json={"persona_id": persona, "campaign_id": "legacy", "outfit": "white t-shirt"},
        headers=headers,
    )
    episodes = client.get(
        "/api/v1/continuity/episodes",
        params={"persona_id": persona, "campaign_id": "legacy"},
        headers=headers,
    ).json()
    assert episodes[0]["snapshot"]["fingerprints"]["wardrobe"] == before
    live = client.get(
        "/api/v1/continuity/resolve",
        params={"persona_id": persona, "campaign_id": "legacy", "episode": 1},
        headers=headers,
    ).json()
    assert live["fingerprints"]["wardrobe"] != before


def test_list_episodes_filters_and_isolates_tenants() -> None:
    _, headers = _register()
    persona = _persona()
    client.post("/api/v1/continuity/episodes", json={"persona_id": persona, "campaign_id": "a"}, headers=headers)
    client.post("/api/v1/continuity/episodes", json={"persona_id": persona, "campaign_id": "b"}, headers=headers)
    client.post("/api/v1/continuity/episodes", json={"persona_id": "CHAR_OTHER", "campaign_id": "a"}, headers=headers)
    assert len(client.get("/api/v1/continuity/episodes", headers=headers).json()) == 3
    assert len(client.get("/api/v1/continuity/episodes", params={"persona_id": persona}, headers=headers).json()) == 2
    assert len(client.get("/api/v1/continuity/episodes", params={"campaign_id": "b"}, headers=headers).json()) == 1
    _, other = _register(tag="continuity-other")
    assert client.get("/api/v1/continuity/episodes", headers=other).json() == []


def test_create_episode_validates() -> None:
    _, headers = _register()
    assert client.post("/api/v1/continuity/episodes", json={"persona_id": ""}, headers=headers).status_code == 422
    assert client.post("/api/v1/continuity/episodes", json={"persona_id": _persona(), "episode": 0}, headers=headers).status_code == 422


# ---------------------------------------------------------------------------
# Every route answers 404 without a workspace (tenant deleted mid-session)
# ---------------------------------------------------------------------------


def _headers_without_workspace() -> dict[str, str]:
    email, headers = _register(tag="continuity-nows")
    with SessionLocal() as db:
        user_id = db.scalar(select(User).where(User.email == email)).id
        db.execute(sa_delete(Workspace).where(Workspace.owner_id == user_id))
        db.commit()
    return headers


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("PUT", "/api/v1/continuity/identity", {"persona_id": "X", "face": "f"}),
        ("GET", "/api/v1/continuity/identity/X", None),
        ("PUT", "/api/v1/continuity/wardrobe", {"persona_id": "X", "outfit": "o"}),
        ("GET", "/api/v1/continuity/wardrobe?persona_id=X", None),
        ("PUT", "/api/v1/continuity/location", {"persona_id": "X", "showroom": "s"}),
        ("GET", "/api/v1/continuity/location?persona_id=X", None),
        ("PUT", "/api/v1/continuity/vehicle", {"persona_id": "X", "vehicle": "v", "color": "c"}),
        ("GET", "/api/v1/continuity/vehicle?persona_id=X", None),
        ("PUT", "/api/v1/continuity/voice", {"persona_id": "X", "voice_profile": "v"}),
        ("GET", "/api/v1/continuity/voice/X", None),
        ("GET", "/api/v1/continuity/resolve?persona_id=X", None),
        ("POST", "/api/v1/continuity/episodes", {"persona_id": "X"}),
    ],
)
def test_routes_without_a_workspace_answer_404(method: str, path: str, body: dict | None) -> None:
    headers = _headers_without_workspace()
    response = client.request(method, path, json=body, headers=headers) if body else client.request(method, path, headers=headers)
    assert response.status_code == 404


def test_list_episodes_without_a_workspace_is_empty() -> None:
    headers = _headers_without_workspace()
    assert client.get("/api/v1/continuity/episodes", headers=headers).json() == []
