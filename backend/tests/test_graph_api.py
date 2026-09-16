"""V3.1 — the twelve graph routes: CRUD, search, traversal, context, seed.

End to end over HTTP: every test registers a fresh user (hence a fresh
workspace), so workspaces isolate tenants the way production does. The suite
pins status codes (201/204/401/404/409/422), the audit rows each mutation
writes, the canonical-relation normalisation on the wire, the semantic tiers
through the seeded demonstration graph, and the character-context phrases the
Director AI will consume.
"""
from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete as sa_delete, select

from app.db import SessionLocal
from app.main import app
from app.models import AuditLog, User, Workspace

client = TestClient(app)


def _register(tag: str = "graph") -> tuple[str, dict[str, str]]:
    email = f"{tag}-{uuid.uuid4()}@example.com"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "name": "Graph Test", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return email, {"Authorization": f"Bearer {token}"}


def _seed(headers: dict[str, str]) -> dict:
    response = client.post("/api/v1/graph/seed", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _create_node(headers: dict[str, str], name: str | None = None, entity_type: str = "character", **extra):
    payload = {"name": name if name is not None else f"Node {uuid.uuid4().hex[:8]}", "entity_type": entity_type, **extra}
    return client.post("/api/v1/graph/nodes", json=payload, headers=headers)


def _latest(action: str) -> AuditLog | None:
    with SessionLocal() as db:
        return db.scalar(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.created_at.desc())
        )


def _node_id_by_character(headers: dict[str, str]) -> str:
    response = client.get("/api/v1/graph/nodes", params={"entity_type": "character"}, headers=headers)
    assert response.status_code == 200
    return response.json()[0]["id"]


# --------------------------------------------------------------------- nodes


def test_create_node_returns_the_persisted_shape_and_audits() -> None:
    _, headers = _register()
    response = _create_node(
        headers, name="Petrick Test", attributes={"role": "Founder"}, aliases=["PT"]
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {
        "id",
        "workspace_id",
        "entity_type",
        "name",
        "slug",
        "attributes",
        "aliases",
        "created_at",
        "updated_at",
    }
    assert (body["name"], body["entity_type"], body["slug"]) == ("Petrick Test", "character", "petrick-test")
    assert body["attributes"] == {"role": "Founder"}
    assert body["aliases"] == ["PT"]
    assert body["created_at"] and body["updated_at"]

    entry = _latest("graph.node.created")
    assert entry is not None
    assert entry.actor_id and entry.resource_type == "graph_node"
    assert entry.resource_id == body["id"]
    assert entry.workspace_id == body["workspace_id"]
    assert json.loads(entry.detail or "{}") == {"entity_type": "character", "slug": "petrick-test"}


def test_create_node_conflicts_on_taken_slugs() -> None:
    _, headers = _register()
    assert _create_node(headers, name="Duplicado").status_code == 201
    assert _create_node(headers, name="Duplicado").status_code == 409
    assert _create_node(headers, name="Other", slug="custom").status_code == 201
    assert _create_node(headers, name="Another", slug="custom").status_code == 409


def test_create_node_validates() -> None:
    _, headers = _register()
    assert _create_node(headers, entity_type="starship").status_code == 422
    assert _create_node(headers, name=" ").status_code == 422
    assert _create_node(headers, name="").status_code == 422
    response = client.post(
        "/api/v1/graph/nodes",
        json={"name": "Bad attrs", "entity_type": "character", "attributes": ["x"]},
        headers=headers,
    )
    assert response.status_code == 422


def test_get_node_and_foreign_ids_404() -> None:
    _, headers = _register()
    created = _create_node(headers, name="Findable").json()
    response = client.get(f"/api/v1/graph/nodes/{created['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Findable"
    assert client.get("/api/v1/graph/nodes/missing", headers=headers).status_code == 404

    _, foreign = _register(tag="graph-foreign")
    assert client.get(f"/api/v1/graph/nodes/{created['id']}", headers=foreign).status_code == 404


def test_list_nodes_filters_paginates_and_isolates() -> None:
    _, headers = _register()
    _seed(headers)
    response = client.get("/api/v1/graph/nodes", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 9

    vehicles = client.get(
        "/api/v1/graph/nodes", params={"entity_type": "vehicle"}, headers=headers
    ).json()
    assert [node["name"] for node in vehicles] == ["RAM"]
    assert (
        client.get("/api/v1/graph/nodes", params={"entity_type": "starship"}, headers=headers).status_code
        == 422
    )
    page = client.get("/api/v1/graph/nodes", params={"limit": 3, "offset": 2}, headers=headers).json()
    assert len(page) == 3

    _, foreign = _register(tag="graph-foreign")
    assert client.get("/api/v1/graph/nodes", headers=foreign).json() == []


def test_update_node_replaces_wholesale_and_audits_sorted_fields() -> None:
    _, headers = _register()
    created = _create_node(headers, name="Old", attributes={"gone": True}).json()
    response = client.patch(
        f"/api/v1/graph/nodes/{created['id']}",
        json={"name": "  New  ", "entity_type": "brand", "attributes": {"fresh": 1}, "aliases": ["N"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["name"], body["entity_type"]) == ("New", "brand")
    assert body["attributes"] == {"fresh": 1}
    assert body["aliases"] == ["N"]
    assert body["slug"] == created["slug"], "the slug is immutable"

    entry = _latest("graph.node.updated")
    assert entry is not None and entry.resource_id == created["id"]
    assert json.loads(entry.detail or "{}") == {
        "fields": ["aliases", "attributes", "entity_type", "name"]
    }


def test_update_node_ignores_unknown_keys_and_validates() -> None:
    _, headers = _register()
    created = _create_node(headers, name="Stable").json()
    response = client.patch(
        f"/api/v1/graph/nodes/{created['id']}", json={"name": "Again", "bogus": 1}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Again"
    assert (
        client.patch(
            f"/api/v1/graph/nodes/{created['id']}", json={"name": " "}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/graph/nodes/{created['id']}", json={"entity_type": "starship"}, headers=headers
        ).status_code
        == 422
    )
    assert client.patch("/api/v1/graph/nodes/missing", json={"name": "x"}, headers=headers).status_code == 404

    _, foreign = _register(tag="graph-foreign")
    assert (
        client.patch(f"/api/v1/graph/nodes/{created['id']}", json={"name": "x"}, headers=foreign).status_code
        == 404
    )


def test_delete_node_cascades_edges_and_audits() -> None:
    _, headers = _register()
    _seed(headers)
    petrick_id = _node_id_by_character(headers)
    assert client.delete(f"/api/v1/graph/nodes/{petrick_id}", headers=headers).status_code == 204
    assert client.get(f"/api/v1/graph/nodes/{petrick_id}", headers=headers).status_code == 404
    remaining = client.get("/api/v1/graph/edges", headers=headers).json()
    assert len(remaining) == 7, "Petrick's four incident edges went with the node"
    assert client.delete(f"/api/v1/graph/nodes/{petrick_id}", headers=headers).status_code == 404

    entry = _latest("graph.node.deleted")
    assert entry is not None and entry.resource_id == petrick_id


# --------------------------------------------------------------------- edges


def _pair(headers: dict[str, str]) -> tuple[dict, dict]:
    first = _create_node(headers, name=f"First {uuid.uuid4().hex[:8]}").json()
    second = _create_node(headers, name=f"Second {uuid.uuid4().hex[:8]}", entity_type="vehicle").json()
    return first, second


def test_create_edge_normalises_and_audits() -> None:
    _, headers = _register()
    first, second = _pair(headers)
    response = client.post(
        "/api/v1/graph/edges",
        json={"source_id": first["id"], "target_id": second["id"], "relation": "dirige"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["relation"], body["inverse"]) == ("drives", "driven_by")
    assert body["workspace_id"] == first["workspace_id"]

    entry = _latest("graph.edge.created")
    assert entry is not None and entry.resource_id == body["id"]
    assert json.loads(entry.detail or "{}") == {"relation": "drives"}


def test_create_edge_guards_endpoints_loops_duplicates_and_vocabulary() -> None:
    _, headers = _register()
    first, second = _pair(headers)
    payload = {"source_id": first["id"], "target_id": second["id"], "relation": "uses"}
    assert client.post("/api/v1/graph/edges", json=payload, headers=headers).status_code == 201
    assert client.post("/api/v1/graph/edges", json=payload, headers=headers).status_code == 409
    assert (
        client.post(
            "/api/v1/graph/edges",
            json={**payload, "source_id": "missing"},
            headers=headers,
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/graph/edges",
            json={**payload, "target_id": "missing"},
            headers=headers,
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/graph/edges",
            json={"source_id": first["id"], "target_id": first["id"], "relation": "uses"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/graph/edges",
            json={**payload, "relation": "teleports"},
            headers=headers,
        ).status_code
        == 422
    )


def test_create_edge_rejects_foreign_endpoints() -> None:
    _, headers = _register()
    first, _ = _pair(headers)
    _, foreign = _register(tag="graph-foreign")
    outsider = _create_node(foreign, name=f"Outsider {uuid.uuid4().hex[:8]}").json()
    response = client.post(
        "/api/v1/graph/edges",
        json={"source_id": first["id"], "target_id": outsider["id"], "relation": "uses"},
        headers=headers,
    )
    assert response.status_code == 404


def test_list_edges_filters_and_paginates() -> None:
    _, headers = _register()
    _seed(headers)
    assert len(client.get("/api/v1/graph/edges", headers=headers).json()) == 11
    drives = client.get("/api/v1/graph/edges", params={"relation": "dirige"}, headers=headers).json()
    assert len(drives) == 1 and drives[0]["relation"] == "drives"
    petrick_id = _node_id_by_character(headers)
    from_petrick = client.get(
        "/api/v1/graph/edges", params={"source_id": petrick_id}, headers=headers
    ).json()
    assert len(from_petrick) == 3
    assert (
        client.get("/api/v1/graph/edges", params={"relation": "teleports"}, headers=headers).status_code
        == 422
    )
    page = client.get("/api/v1/graph/edges", params={"limit": 5}, headers=headers).json()
    assert len(page) == 5


def test_delete_edge_keeps_the_nodes_and_audits() -> None:
    _, headers = _register()
    first, second = _pair(headers)
    edge = client.post(
        "/api/v1/graph/edges",
        json={"source_id": first["id"], "target_id": second["id"], "relation": "uses"},
        headers=headers,
    ).json()
    assert client.delete(f"/api/v1/graph/edges/{edge['id']}", headers=headers).status_code == 204
    assert client.get(f"/api/v1/graph/nodes/{first['id']}", headers=headers).status_code == 200
    assert client.get(f"/api/v1/graph/nodes/{second['id']}", headers=headers).status_code == 200
    assert client.delete(f"/api/v1/graph/edges/{edge['id']}", headers=headers).status_code == 404

    _, foreign = _register(tag="graph-foreign")
    assert client.delete(f"/api/v1/graph/edges/{edge['id']}", headers=foreign).status_code == 404

    entry = _latest("graph.edge.deleted")
    assert entry is not None and entry.resource_id == edge["id"]


# --------------------------------------------------------------------- query


def test_query_answers_the_brief_questions() -> None:
    _, headers = _register()
    _seed(headers)
    response = client.get("/api/v1/graph/query", params={"q": "RAM branca"}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert (body["query"], body["entity_type"]) == ("RAM branca", None)
    assert body["count"] == len(body["matches"]) >= 1
    first = body["matches"][0]
    assert (first["node"]["name"], first["node"]["entity_type"]) == ("RAM", "vehicle")
    assert first["score"] == 55
    assert first["matched_fields"] == ["alias", "attributes.color", "name"]

    exact = client.get("/api/v1/graph/query", params={"q": "Showroom"}, headers=headers).json()
    assert (exact["matches"][0]["node"]["name"], exact["matches"][0]["score"]) == ("Showroom", 100)
    assert exact["matches"][0]["node"]["entity_type"] == "location"


def test_query_validates_filtering_and_empty_results() -> None:
    _, headers = _register()
    _seed(headers)
    assert client.get("/api/v1/graph/query", params={"q": "  "}, headers=headers).status_code == 422
    empty = client.get("/api/v1/graph/query", params={"q": "zzzqqq"}, headers=headers).json()
    assert (empty["count"], empty["matches"]) == (0, [])
    filtered = client.get(
        "/api/v1/graph/query", params={"q": "goiania", "entity_type": "location"}, headers=headers
    ).json()
    assert filtered["entity_type"] == "location"
    assert {match["node"]["entity_type"] for match in filtered["matches"]} == {"location"}

    _, foreign = _register(tag="graph-foreign")
    assert client.get("/api/v1/graph/query", params={"q": "RAM"}, headers=foreign).json()["count"] == 0


# ----------------------------------------------------------------- traversal


def test_neighbors_walks_both_directions() -> None:
    _, headers = _register()
    _seed(headers)
    petrick_id = _node_id_by_character(headers)
    body = client.get(f"/api/v1/graph/neighbors/{petrick_id}", headers=headers).json()
    assert (body["node"]["name"], body["depth"], body["direction"]) == ("Petrick", 1, "both")
    assert len(body["nodes"]) == 5
    assert len(body["edges"]) == 4

    out = client.get(
        f"/api/v1/graph/neighbors/{petrick_id}", params={"direction": "out"}, headers=headers
    ).json()
    assert (len(out["nodes"]), len(out["edges"])) == (4, 3)
    inward = client.get(
        f"/api/v1/graph/neighbors/{petrick_id}", params={"direction": "in"}, headers=headers
    ).json()
    assert (len(inward["nodes"]), len(inward["edges"])) == (2, 1)


def test_neighbors_depth_two_reaches_further() -> None:
    _, headers = _register()
    _seed(headers)
    showroom = client.get(
        "/api/v1/graph/query", params={"q": "Showroom"}, headers=headers
    ).json()["matches"][0]["node"]
    body = client.get(
        f"/api/v1/graph/neighbors/{showroom['id']}", params={"depth": 2}, headers=headers
    ).json()
    assert len(body["nodes"]) == 7
    assert len(body["edges"]) == 7


def test_neighbors_guards() -> None:
    _, headers = _register()
    assert client.get("/api/v1/graph/neighbors/missing", headers=headers).status_code == 404
    _, other = _register(tag="graph-other")
    node = _create_node(other).json()
    assert client.get(f"/api/v1/graph/neighbors/{node['id']}", headers=headers).status_code == 404
    assert (
        client.get(
            f"/api/v1/graph/neighbors/{node['id']}", params={"direction": "sideways"}, headers=other
        ).status_code
        == 422
    )
    assert (
        client.get(f"/api/v1/graph/neighbors/{node['id']}", params={"depth": 5}, headers=other).status_code
        == 422
    )


# ------------------------------------------------------------------- context


def test_character_context_serves_identity_relations_and_phrases() -> None:
    _, headers = _register()
    _seed(headers)
    response = client.get("/api/v1/graph/characters/Petrick/context", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["found"] is True
    assert body["persona_id"] == "CHAR_PETRICK"
    assert body["node"]["name"] == "Petrick"
    assert body["phrases"] == [
        "Legacy Launch apresenta Petrick",
        "Petrick dirige RAM",
        "Petrick gerencia Legacy",
        "Petrick veste Legacy Jacket",
    ]
    assert [
        (item["relation"], item["direction"], item["peer"]["name"], item["phrase"])
        for item in body["relations"]
    ] == [
        ("manages", "out", "Legacy", "Petrick gerencia Legacy"),
        ("wears", "out", "Legacy Jacket", "Petrick veste Legacy Jacket"),
        ("features", "in", "Legacy Launch", "Legacy Launch apresenta Petrick"),
        ("drives", "out", "RAM", "Petrick dirige RAM"),
    ]
    assert body["relation_counts"] == {"manages": 1, "wears": 1, "features": 1, "drives": 1}


def test_character_context_without_a_graph_entry_but_with_a_persona() -> None:
    _, headers = _register()
    body = client.get("/api/v1/graph/characters/Jefferson/context", headers=headers).json()
    assert body["found"] is False
    assert body["persona_id"] == "CHAR_JEFFERSON"
    assert body["node"] is None
    assert (body["phrases"], body["relations"], body["relation_counts"]) == ([], [], {})


def test_character_context_for_graph_only_names() -> None:
    _, headers = _register()
    solo = f"Solo {uuid.uuid4().hex[:8]}"
    prop = f"Prop {uuid.uuid4().hex[:8]}"
    character = _create_node(headers, name=solo).json()
    gadget = _create_node(headers, name=prop, entity_type="prop").json()
    client.post(
        "/api/v1/graph/edges",
        json={"source_id": character["id"], "target_id": gadget["id"], "relation": "wears"},
        headers=headers,
    )
    body = client.get(f"/api/v1/graph/characters/{solo}/context", headers=headers).json()
    assert body["found"] is True
    assert body["persona_id"] is None
    assert body["phrases"] == [f"{solo} veste {prop}"]
    assert len(body["relations"]) == 1


def test_character_context_for_unknown_names_and_foreign_workspaces() -> None:
    _, headers = _register()
    _seed(headers)
    body = client.get("/api/v1/graph/characters/Nobody Xyz/context", headers=headers).json()
    assert body["found"] is False
    assert body["persona_id"] is None
    assert (body["phrases"], body["relations"]) == ([], [])

    _, foreign = _register(tag="graph-foreign")
    assert (
        client.get("/api/v1/graph/characters/Petrick/context", headers=foreign).json()["found"]
        is False
    )


# ---------------------------------------------------------------------- seed


def test_seed_is_idempotent_and_audited() -> None:
    _, headers = _register()
    first = _seed(headers)
    assert first == {"created_nodes": 9, "created_edges": 11, "skipped_nodes": 0, "skipped_edges": 0}
    entry = _latest("graph.seeded")
    assert entry is not None and entry.resource_type == "graph"
    assert json.loads(entry.detail or "{}") == first
    second = _seed(headers)
    assert second == {
        "created_nodes": 0,
        "created_edges": 0,
        "skipped_nodes": 9,
        "skipped_edges": 11,
    }
    assert json.loads((_latest("graph.seeded") or entry).detail or "{}") == second


# ------------------------------------------------------------------ protection


def test_every_graph_route_requires_identity() -> None:
    calls = [
        ("post", "/api/v1/graph/nodes", {"name": "x", "entity_type": "character"}),
        ("get", "/api/v1/graph/nodes", None),
        ("get", "/api/v1/graph/nodes/x", None),
        ("patch", "/api/v1/graph/nodes/x", {"name": "y"}),
        ("delete", "/api/v1/graph/nodes/x", None),
        ("post", "/api/v1/graph/edges", {"source_id": "a", "target_id": "b", "relation": "uses"}),
        ("get", "/api/v1/graph/edges", None),
        ("delete", "/api/v1/graph/edges/x", None),
        ("get", "/api/v1/graph/query?q=x", None),
        ("get", "/api/v1/graph/neighbors/x", None),
        ("get", "/api/v1/graph/characters/x/context", None),
        ("post", "/api/v1/graph/seed", None),
    ]
    for method, path, payload in calls:
        response = client.request(method, path, json=payload)
        assert response.status_code == 401, f"{method.upper()} {path} answered {response.status_code}"


def test_routes_without_a_workspace() -> None:
    email, headers = _register(tag="graph-nows")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        db.execute(sa_delete(Workspace).where(Workspace.owner_id == user.id))
        db.commit()

    assert client.get("/api/v1/graph/nodes", headers=headers).json() == []
    assert client.get("/api/v1/graph/edges", headers=headers).json() == []
    assert client.get("/api/v1/graph/query", params={"q": "x"}, headers=headers).json()["count"] == 0

    missing = [
        ("post", "/api/v1/graph/nodes", {"name": "x", "entity_type": "character"}),
        ("get", "/api/v1/graph/nodes/x", None),
        ("patch", "/api/v1/graph/nodes/x", {"name": "y"}),
        ("delete", "/api/v1/graph/nodes/x", None),
        ("post", "/api/v1/graph/edges", {"source_id": "a", "target_id": "b", "relation": "uses"}),
        ("delete", "/api/v1/graph/edges/x", None),
        ("get", "/api/v1/graph/neighbors/x", None),
        ("get", "/api/v1/graph/characters/x/context", None),
        ("post", "/api/v1/graph/seed", None),
    ]
    for method, path, payload in missing:
        response = client.request(method, path, json=payload, headers=headers)
        assert response.status_code == 404, f"{method.upper()} {path} answered {response.status_code}"


def test_query_maps_search_errors_to_422(monkeypatch) -> None:
    from app.graph import semantic_query as semantic_module
    from app.graph.graph_models import GraphValidationError

    _, headers = _register(tag="graph-query-err")

    def _boom(self, text, *, entity_type=None, limit=10):
        raise GraphValidationError("boom")

    monkeypatch.setattr(semantic_module.SemanticQuery, "query", _boom)
    response = client.get("/api/v1/graph/query", params={"q": "x"}, headers=headers)
    assert response.status_code == 422
