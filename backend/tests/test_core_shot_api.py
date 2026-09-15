"""ETAPA 6 — the shot library HTTP surface (the visual shot browser).

SHOT_LIBRARY.md: "A shot is a reusable direction preset, not a prompt blob."
These tests pin the browser contract and the fact that no shot is ever invented
for an unknown code.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_the_library_reaches_its_target_over_http() -> None:
    body = client.get("/api/v1/core/shots/audit").json()
    assert body["total"] == 300
    assert body["target"] == 300
    assert body["meets_target"] is True
    assert body["published"] == 10
    assert body["expanded"] == 290


def test_the_library_is_fully_compliant_with_the_bible() -> None:
    body = client.get("/api/v1/core/shots/audit").json()
    assert body["violations"] == {}
    assert body["duplicates"] == []


def test_families_are_listed_with_counts() -> None:
    body = client.get("/api/v1/core/shots/families").json()
    counts = {entry["family"]: entry["count"] for entry in body}
    assert counts["published"] == 10
    assert counts["establishing"] == 25
    assert counts["documentary"] == 24
    assert sum(counts.values()) == 300


def test_families_carry_human_labels() -> None:
    body = client.get("/api/v1/core/shots/families").json()
    labels = {entry["family"]: entry["label"] for entry in body}
    assert labels["tension"] == "Tension & suspense"
    assert labels["published"] == "Published presets"


def test_the_catalog_is_paginated_by_default() -> None:
    assert len(client.get("/api/v1/core/shots").json()) == 50


def test_the_limit_is_respected() -> None:
    assert len(client.get("/api/v1/core/shots", params={"limit": 7}).json()) == 7


def test_a_negative_limit_returns_nothing_rather_than_erroring() -> None:
    assert client.get("/api/v1/core/shots", params={"limit": -5}).json() == []


def test_the_library_can_be_filtered_by_family() -> None:
    body = client.get("/api/v1/core/shots", params={"family": "tension", "limit": 300}).json()
    assert body
    assert all(shot["family"] == "tension" for shot in body)


def test_the_library_can_be_filtered_by_focal_length() -> None:
    body = client.get("/api/v1/core/shots", params={"lens_mm": 135, "limit": 300}).json()
    assert body
    assert all(shot["lens_mm"] == 135 for shot in body)


def test_the_library_can_be_filtered_by_frame() -> None:
    body = client.get("/api/v1/core/shots", params={"frame": "extreme close-up", "limit": 300}).json()
    assert body
    assert all(shot["frame"] == "extreme close-up" for shot in body)


def test_the_library_can_be_filtered_by_motivation() -> None:
    body = client.get("/api/v1/core/shots", params={"motivation": "escape", "limit": 300}).json()
    assert body
    assert all("escape" in shot["motivations"] for shot in body)


def test_filters_combine() -> None:
    body = client.get(
        "/api/v1/core/shots", params={"family": "tension", "lens_mm": 85, "limit": 300}
    ).json()
    assert body
    assert all(shot["family"] == "tension" and shot["lens_mm"] == 85 for shot in body)


def test_free_text_search_reaches_intention_and_continuity() -> None:
    assert any(shot["code"] == "SH136" for shot in client.get("/api/v1/core/shots", params={"q": "grief"}).json())
    assert client.get("/api/v1/core/shots", params={"q": "eyeline", "limit": 300}).json()


def test_an_unknown_query_returns_an_empty_list() -> None:
    assert client.get("/api/v1/core/shots", params={"q": "zzzz-no-match"}).json() == []


def test_a_shot_carries_the_grammar_read_off_it() -> None:
    body = client.get("/api/v1/core/shots/SH300").json()
    assert body["code"] == "SH300"
    assert body["name"] == "Final Survey"
    assert body["lens"] == "24mm"
    assert body["lens_mm"] == 24
    assert body["motivations"] == ["reveal", "escape"]
    assert body["family"] == "documentary"
    assert body["continuity"] == "must echo SH283's survey"


def test_lookup_is_case_insensitive() -> None:
    assert client.get("/api/v1/core/shots/sh300").json()["code"] == "SH300"


def test_an_unknown_shot_is_404_never_an_invention() -> None:
    """ShotResolver's rule: inventing camera language is worse than omitting it."""

    response = client.get("/api/v1/core/shots/SH999")
    assert response.status_code == 404
    assert "unknown shot code" in response.json()["detail"]


def test_the_ten_published_presets_are_still_reachable() -> None:
    for code in ("SH001", "SH014", "SH032", "SH051", "SH089", "SH120", "SH121", "SH122", "SH123", "SH124"):
        body = client.get(f"/api/v1/core/shots/{code}").json()
        assert body["code"] == code
        assert body["lens"], code


def test_a_published_shot_does_not_carry_invented_expansion_fields() -> None:
    body = client.get("/api/v1/core/shots/SH001").json()
    assert body["frame"] == ""
    assert body["lighting"] == ""
    assert body["continuity"] == ""
    assert body["family"] == ""


def test_the_static_routes_are_declared_before_the_dynamic_one() -> None:
    """/shots/families and /shots/audit must not be swallowed by /shots/{code}."""

    assert client.get("/api/v1/core/shots/families").status_code == 200
    assert client.get("/api/v1/core/shots/audit").status_code == 200
    assert client.get("/api/v1/core/shots/families").json()[0]["family"] != "families"


def test_a_shot_compiles_into_a_generation_spec() -> None:
    """End to end: a new shot drives the Core, not just the browser."""

    body = client.post("/api/v1/core/compile", json={"prompt": "a portrait", "shot": "SH300"}).json()
    assert body["trace"]["shot_code"] == "SH300"
    assert body["camera"], "the shot must contribute camera language"


def test_a_published_shot_still_compiles_exactly_as_before() -> None:
    body = client.post("/api/v1/core/compile", json={"prompt": "x", "style": "john-wick", "shot": "SH001"}).json()
    assert body["trace"]["shot_code"] == "SH001"
    assert body["trace"]["sources"]["camera"] == "shot"


def test_an_unknown_shot_does_not_silently_fall_back() -> None:
    known = client.post("/api/v1/core/compile", json={"prompt": "x", "shot": "SH300"}).json()
    unknown = client.post("/api/v1/core/compile", json={"prompt": "x", "shot": "SH999"}).json()
    assert known["trace"]["shot_code"] == "SH300"
    assert unknown["trace"]["shot_code"] is None


def test_the_shot_routes_are_read_only() -> None:
    spec = client.get("/openapi.json").json()["paths"]
    for path, methods in spec.items():
        if path.startswith("/api/v1/core/shots"):
            assert set(methods) == {"get"}, f"{path} exposes {sorted(methods)}"


def test_the_openapi_surface_documents_the_shot_endpoints() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/v1/core/shots",
        "/api/v1/core/shots/families",
        "/api/v1/core/shots/audit",
        "/api/v1/core/shots/{shot_code}",
    ):
        assert path in paths, path


def test_the_shot_routes_contain_no_library_rules() -> None:
    """Routes filter and serialise; the grammar lives in the Core."""

    import inspect

    import app.main as main_module

    for name in ("list_shots", "list_shot_families", "audit_shot_library", "read_shot"):
        body = inspect.getsource(getattr(main_module, name))
        for forbidden in ("violations()", "_derive_", "build_shot", "ShotPreset("):
            assert forbidden not in body, f"{name} implements library logic inline ({forbidden})"
