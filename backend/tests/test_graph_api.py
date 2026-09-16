"""V3.1 — the knowledge graph HTTP surface.

One tenant (unique email per run) exercises every route; writes stay inside
its workspace, canonical catalog rows are asserted read-only, and the four
relationships the sprint names must be visible in the graph.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_REGISTER = client.post(
    "/api/v1/auth/register",
    json={
        "email": f"graph-api-{uuid4()}@example.com",
        "name": "Graph API",
        "password": "strong-pass-123",
    },
)
assert _REGISTER.status_code == 201, _REGISTER.text
HEADERS = {"Authorization": f"Bearer {_REGISTER.json()['access_token']}"}


def _unique(name: str) -> str:
    return f"{name} {uuid4().hex[:8]}"


# ------------------------------------------------------------------- access

def test_graph_routes_require_identity() -> None:
    for path in ("/api/v1/graph", "/api/v1/graph/nodes", "/api/v1/graph/search"):
        assert client.get(path).status_code == 401
    assert client.post("/api/v1/graph/nodes", json={"entity_type": "vehicle", "name": "X"}).status_code == 401


def test_the_full_graph_returns_the_catalog_and_counts() -> None:
    body = client.get("/api/v1/graph", headers=HEADERS).json()
    assert body["counts"]["nodes"] == len(body["nodes"])
    assert body["counts"]["relationships"] == len(body["relationships"])
    assert body["counts"]["nodes"] >= 9
    assert body["counts"]["relationships"] >= 8
    assert body["counts"]["by_type"]["character"] >= 2
    assert body["counts"]["by_type"]["vehicle"] >= 1
    # every edge ships both readings and both endpoint nodes
    for edge in body["relationships"]:
        assert edge["display_label"]
        assert edge["reverse_relation_type"]
        assert edge["source"]["name"] and edge["target"]["name"]
    # the four sprint relationships are in the catalog
    pairs = {(e["source"]["name"], e["relation_type"], e["target"]["name"]) for e in body["relationships"]}
    assert ("Petrick Martins", "dirige", "RAM") in pairs
    assert ("Petrick Martins", "veste", "Legacy Jacket") in pairs
    assert ("Legacy", "pertence", "BroBond") in pairs
    assert ("Showroom", "localizado", "Goiânia") in pairs


# -------------------------------------------------------------------- nodes

def test_create_node_round_trips_and_duplicate_is_409() -> None:
    name = _unique("Test Truck")
    response = client.post(
        "/api/v1/graph/nodes",
        headers=HEADERS,
        json={"entity_type": "vehicle", "name": name, "description": "d", "attributes": {"cor": "azul"}},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["entity_type"] == "vehicle"
    assert body["name"] == name
    assert body["attributes"] == {"cor": "azul"}
    assert body["is_canonical"] is False
    assert client.post(
        "/api/v1/graph/nodes", headers=HEADERS, json={"entity_type": "vehicle", "name": name}
    ).status_code == 409


def test_create_node_refuses_an_unknown_entity_type() -> None:
    response = client.post(
        "/api/v1/graph/nodes",
        headers=HEADERS,
        json={"entity_type": "spaceship", "name": "Enterprise"},
    )
    assert response.status_code == 422


def test_node_detail_is_bidirectional() -> None:
    created = client.post(
        "/api/v1/graph/nodes",
        headers=HEADERS,
        json={"entity_type": "location", "name": _unique("Garage")},
    ).json()
    body = client.get(f"/api/v1/graph/nodes/{created['id']}", headers=HEADERS).json()
    assert body["node"]["id"] == created["id"]
    assert body["relationships"] == [], "a fresh node has no edges yet"
    # attach an edge to a canonical node and read it back from both sides
    ram = next(n for n in client.get("/api/v1/graph", headers=HEADERS).json()["nodes"] if n["name"] == "RAM")
    edge = client.post(
        "/api/v1/graph/relationships",
        headers=HEADERS,
        json={"source_id": created["id"], "target_id": ram["id"], "relation_type": "aparece_em"},
    )
    assert edge.status_code == 201, edge.text
    detail = client.get(f"/api/v1/graph/nodes/{created['id']}", headers=HEADERS).json()
    assert [r["target"]["name"] for r in detail["relationships"]] == ["RAM"]
    ram_detail = client.get(f"/api/v1/graph/nodes/{ram['id']}", headers=HEADERS).json()
    incoming = [r for r in ram_detail["relationships"] if r["source"]["id"] == created["id"]]
    assert len(incoming) == 1
    assert incoming[0]["reverse_relation_type"] == "apresenta"


def test_update_node_patches_fields() -> None:
    created = client.post(
        "/api/v1/graph/nodes", headers=HEADERS, json={"entity_type": "prop", "name": _unique("Camera")}
    ).json()
    updated = client.patch(
        f"/api/v1/graph/nodes/{created['id']}",
        headers=HEADERS,
        json={"description": "hero prop", "attributes": {"lente": "50mm"}},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["description"] == "hero prop"
    assert body["attributes"] == {"lente": "50mm"}
    assert body["name"] == created["name"]


def test_canonical_nodes_are_read_only_over_http() -> None:
    petrick = next(
        n
        for n in client.get("/api/v1/graph/nodes?entity_type=character", headers=HEADERS).json()
        if n["name"] == "Petrick Martins"
    )
    assert petrick["is_canonical"] is True
    assert client.patch(f"/api/v1/graph/nodes/{petrick['id']}", headers=HEADERS, json={"name": "X"}).status_code == 403
    assert client.delete(f"/api/v1/graph/nodes/{petrick['id']}", headers=HEADERS).status_code == 403
    still = client.get(f"/api/v1/graph/nodes/{petrick['id']}", headers=HEADERS)
    assert still.status_code == 200 and still.json()["node"]["name"] == "Petrick Martins"


def test_delete_node_removes_it_and_its_edges() -> None:
    character = client.post(
        "/api/v1/graph/nodes", headers=HEADERS, json={"entity_type": "character", "name": _unique("Sidekick")}
    ).json()
    vehicle = client.post(
        "/api/v1/graph/nodes", headers=HEADERS, json={"entity_type": "vehicle", "name": _unique("Bike")}
    ).json()
    assert (
        client.post(
            "/api/v1/graph/relationships",
            headers=HEADERS,
            json={"source_id": character["id"], "target_id": vehicle["id"], "relation_type": "dirige"},
        ).status_code
        == 201
    )
    assert client.delete(f"/api/v1/graph/nodes/{character['id']}", headers=HEADERS).status_code == 204
    assert client.get(f"/api/v1/graph/nodes/{character['id']}", headers=HEADERS).status_code == 404
    remaining = client.get(f"/api/v1/graph/nodes/{vehicle['id']}", headers=HEADERS).json()
    assert remaining["relationships"] == [], "the edge followed its source into the trash"
    assert client.delete(f"/api/v1/graph/nodes/{character['id']}", headers=HEADERS).status_code == 404


def test_unknown_node_is_404() -> None:
    assert client.get("/api/v1/graph/nodes/no-such-id", headers=HEADERS).status_code == 404
    assert client.patch("/api/v1/graph/nodes/no-such-id", headers=HEADERS, json={"name": "X"}).status_code == 404
    assert client.delete("/api/v1/graph/nodes/no-such-id", headers=HEADERS).status_code == 404


def test_node_filters() -> None:
    client.post(
        "/api/v1/graph/nodes",
        headers=HEADERS,
        json={"entity_type": "brand", "name": _unique("Acme Motors"), "description": "a fictional test brand"},
    )
    brands = client.get("/api/v1/graph/nodes", headers=HEADERS, params={"entity_type": "brand"}).json()
    assert all(node["entity_type"] == "brand" for node in brands)
    found = client.get("/api/v1/graph/nodes", headers=HEADERS, params={"q": "fictional test brand"}).json()
    assert any(node["entity_type"] == "brand" for node in found)


# ------------------------------------------------------------ relationships

def test_relationship_validation_matrix() -> None:
    a = client.post(
        "/api/v1/graph/nodes", headers=HEADERS, json={"entity_type": "character", "name": _unique("Rider")}
    ).json()
    b = client.post(
        "/api/v1/graph/nodes", headers=HEADERS, json={"entity_type": "vehicle", "name": _unique("Moto")}
    ).json()
    # self-loop: 422
    assert (
        client.post(
            "/api/v1/graph/relationships",
            headers=HEADERS,
            json={"source_id": a["id"], "target_id": a["id"], "relation_type": "dirige"},
        ).status_code
        == 422
    )
    # unknown endpoint: 404
    assert (
        client.post(
            "/api/v1/graph/relationships",
            headers=HEADERS,
            json={"source_id": "no-such-node", "target_id": b["id"], "relation_type": "dirige"},
        ).status_code
        == 404
    )
    # empty type: 422 (pydantic min_length)
    assert (
        client.post(
            "/api/v1/graph/relationships",
            headers=HEADERS,
            json={"source_id": a["id"], "target_id": b["id"], "relation_type": "  "},
        ).status_code
        == 422
    )
    # valid create, then duplicate: 409
    created = client.post(
        "/api/v1/graph/relationships",
        headers=HEADERS,
        json={"source_id": a["id"], "target_id": b["id"], "relation_type": "dirige", "description": "t"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["display_label"] == "dirige"
    assert created.json()["reverse_relation_type"] == "é dirigido por"
    assert (
        client.post(
            "/api/v1/graph/relationships",
            headers=HEADERS,
            json={"source_id": a["id"], "target_id": b["id"], "relation_type": "dirige"},
        ).status_code
        == 409
    )


def test_relationship_filters_and_delete() -> None:
    a = client.post(
        "/api/v1/graph/nodes", headers=HEADERS, json={"entity_type": "character", "name": _unique("Pilot")}
    ).json()
    b = client.post(
        "/api/v1/graph/nodes", headers=HEADERS, json={"entity_type": "vehicle", "name": _unique("Jet")}
    ).json()
    edge = client.post(
        "/api/v1/graph/relationships",
        headers=HEADERS,
        json={"source_id": a["id"], "target_id": b["id"], "relation_type": "usa"},
    ).json()
    filtered = client.get(
        "/api/v1/graph/relationships", headers=HEADERS, params={"relation_type": "usa", "source_id": a["id"]}
    ).json()
    assert any(r["id"] == edge["id"] for r in filtered)
    assert all(r["relation_type"] == "usa" and r["source_id"] == a["id"] for r in filtered)
    assert client.delete(f"/api/v1/graph/relationships/{edge['id']}", headers=HEADERS).status_code == 204
    assert client.get("/api/v1/graph/relationships", headers=HEADERS, params={"source_id": a["id"]}).json() == []


def test_canonical_relationship_is_read_only_over_http() -> None:
    edges = client.get("/api/v1/graph/relationships", headers=HEADERS, params={"relation_type": "dirige"}).json()
    canonical = next(r for r in edges if r["is_canonical"])
    response = client.delete(f"/api/v1/graph/relationships/{canonical['id']}", headers=HEADERS)
    assert response.status_code == 403
    assert client.get("/api/v1/graph/relationships", headers=HEADERS, params={"relation_type": "dirige"}).json()


def test_unknown_relationship_delete_is_404() -> None:
    assert client.delete("/api/v1/graph/relationships/no-such-id", headers=HEADERS).status_code == 404


# ------------------------------------------------------------------- search

def test_semantic_search_ram_branca_returns_the_vehicle() -> None:
    body = client.get("/api/v1/graph/search", headers=HEADERS, params={"q": "RAM branca"}).json()
    assert body["query"] == "RAM branca"
    assert body["results"], "the sprint example must hit"
    top = body["results"][0]
    assert top["node"]["entity_type"] == "vehicle"
    assert top["node"]["name"] == "RAM"
    assert top["node"]["attributes"]["cor"] == "branca"
    assert top["score"] > 0
    assert top["relationships"], "the result is the complete entity, with its edges"


def test_semantic_search_showroom_returns_the_location() -> None:
    body = client.get("/api/v1/graph/search", headers=HEADERS, params={"q": "Showroom"}).json()
    assert body["results"][0]["node"]["entity_type"] == "location"
    assert body["results"][0]["node"]["name"] == "Showroom"


def test_semantic_search_unknown_phrase_is_empty() -> None:
    body = client.get("/api/v1/graph/search", headers=HEADERS, params={"q": "xyzzy"}).json()
    assert body["results"] == []


def test_semantic_search_requires_a_query() -> None:
    assert client.get("/api/v1/graph/search", headers=HEADERS, params={"q": ""}).status_code == 422
    assert client.get("/api/v1/graph/search", headers=HEADERS, params={"q": "RAM", "limit": 0}).status_code == 422


def test_semantic_search_entity_type_filter() -> None:
    body = client.get(
        "/api/v1/graph/search", headers=HEADERS, params={"q": "Legacy", "entity_type": "wardrobe"}
    ).json()
    assert all(node["node"]["entity_type"] == "wardrobe" for node in body["results"])
    assert any(node["node"]["name"] == "Legacy Jacket" for node in body["results"])
