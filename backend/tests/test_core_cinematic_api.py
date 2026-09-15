"""ETAPA 5 — the cinematic library HTTP surface.

Read-only reference data plus normative checks. These tests pin the contract a
director-facing UI will build on.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_the_lens_language_is_served() -> None:
    body = client.get("/api/v1/core/cinematic/lenses").json()
    assert [entry["focal_mm"] for entry in body] == [24, 35, 50, 85, 135]
    assert body[4]["semantics"] == ["observation", "isolation", "premium editorial detail"]


def test_lenses_can_be_found_by_purpose() -> None:
    body = client.get("/api/v1/core/cinematic/lenses/for", params={"purpose": "isolation"}).json()
    assert [entry["focal_mm"] for entry in body] == [135]


def test_an_unknown_purpose_returns_an_empty_list_not_a_guess() -> None:
    assert client.get("/api/v1/core/cinematic/lenses/for", params={"purpose": "explosions"}).json() == []
    assert client.get("/api/v1/core/cinematic/lenses/for").json() == []


def test_framing_carries_both_sizes_and_angles() -> None:
    body = client.get("/api/v1/core/cinematic/framing").json()
    assert [frame["name"] for frame in body["frames"]] == [
        "establishing shot",
        "medium shot",
        "close-up",
        "extreme close-up",
    ]
    assert {angle["name"]: angle["creates"] for angle in body["angles"]} == {
        "low angle": "presence",
        "high angle": "vulnerability",
        "centered symmetry": "authority",
    }


def test_lighting_exposes_roles_and_the_haze_constraint() -> None:
    body = client.get("/api/v1/core/cinematic/lighting").json()
    roles = {light["name"]: light["role"] for light in body["lights"]}
    assert roles["volumetric haze"] == "reveals depth"
    haze = next(light for light in body["lights"] if light["name"] == "volumetric haze")
    assert "never as decoration" in haze["constraint"]
    assert {quality["name"]: quality["supports"] for quality in body["time_qualities"]} == {
        "blue hour": "reflection",
        "hard noon": "discipline",
        "warm side light": "legacy",
    }


def test_the_five_motivations_are_served() -> None:
    body = client.get("/api/v1/core/cinematic/motivations").json()
    assert [entry["name"] for entry in body] == [
        "reveal",
        "approach",
        "escape",
        "observation",
        "transformation",
    ]


def test_a_still_camera_is_reported_as_owing_no_motivation() -> None:
    body = client.get("/api/v1/core/cinematic/motivations/of", params={"motion": "static"}).json()
    assert body == {
        "motion": "static",
        "motivations": [],
        "still": True,
        "motivated": True,
        "claims_without_naming": False,
    }


def test_a_dolly_is_recognised_as_an_approach() -> None:
    """Regression: "elegant slow dolly" was missed because only "dolly-in" matched."""

    body = client.get("/api/v1/core/cinematic/motivations/of", params={"motion": "elegant slow dolly, measured"}).json()
    assert body["motivations"] == ["approach"]
    assert body["motivated"] is True


def test_a_135mm_lens_is_not_read_as_35mm() -> None:
    """Regression: SH122's "135mm" was parsed as 35mm by a substring match."""

    body = client.get("/api/v1/core/cinematic/explain", params={"style": "cinematic-realism"}).json()
    assert body["lens_mm"] == 85

    from app.core.cinematic_library import CinematicLibrary

    assert CinematicLibrary().focal_of("135mm macro-like compression") == 135


def test_an_unmotivated_move_is_reported_honestly() -> None:
    body = client.get("/api/v1/core/cinematic/motivations/of", params={"motion": "sudden zoom"}).json()
    assert body["motivations"] == []
    assert body["still"] is False
    assert body["motivated"] is False


def test_the_audit_covers_the_whole_library() -> None:
    body = client.get("/api/v1/core/cinematic/audit").json()
    assert body["styles_audited"] == 7
    # ETAPA 6 grew the library from 10 published presets to 300.
    assert body["shots_audited"] == 300
    assert len(body["compliant"]) + len(body["flagged"]) == 307
    assert "motion-motivated" in body["rules"]
    assert "lens-declared" in body["rules"]


def test_the_audit_reports_the_librarys_own_exceptions() -> None:
    body = client.get("/api/v1/core/cinematic/audit").json()
    assert "marvel-trailer" in body["flagged"]
    rules = {item["rule"] for item in body["flagged"]["marvel-trailer"]}
    assert "teal-amber-sparingly" in rules


def test_the_audit_raises_no_violation_against_the_published_seeds() -> None:
    """Pinned so tightening a keyword set cannot start condemning the library."""

    body = client.get("/api/v1/core/cinematic/audit").json()
    for identifier, items in body["flagged"].items():
        for item in items:
            assert item["status"] == "attention", f"{identifier}: {item}"


def test_every_finding_cites_the_bible() -> None:
    body = client.get("/api/v1/core/cinematic/audit").json()
    for items in body["flagged"].values():
        for item in items:
            assert item["source"] == "knowledge_base/CINEMATIC_BIBLE.md"


def test_explain_speaks_the_grammar() -> None:
    body = client.get("/api/v1/core/cinematic/explain", params={"style": "john-wick"}).json()
    assert body["style_id"] == "john-wick"
    assert "35mm for human context, movement, documentary intimacy" in body["explanation"]
    assert body["lens_mm"] == 35
    assert body["motivations"]


def test_explain_of_an_unknown_style_falls_back_like_the_compiler_would() -> None:
    """The explanation must never describe a look that will not be rendered."""

    body = client.get("/api/v1/core/cinematic/explain", params={"style": "does-not-exist"}).json()
    assert body["style_id"] == "brobond-neutral"


def test_explain_without_a_style_uses_the_brobond_default() -> None:
    assert client.get("/api/v1/core/cinematic/explain").json()["style_id"] == "cinematic-realism"


def test_grain_drift_across_an_episode_is_a_violation() -> None:
    body = client.get(
        "/api/v1/core/cinematic/consistency", params={"styles": ["john-wick", "neo-tokyo"]}
    ).json()
    assert body["consistent"] is False
    assert body["scenes"] == 2
    violation = next(item for item in body["findings"] if item["rule"] == "grain-consistent-across-episode")
    assert violation["status"] == "violation"


def test_one_style_repeated_is_consistent() -> None:
    body = client.get(
        "/api/v1/core/cinematic/consistency", params={"styles": ["john-wick", "john-wick", "john-wick"]}
    ).json()
    assert body["consistent"] is True
    assert body["findings"] == []
    assert body["scenes"] == 3


def test_consistency_without_scenes_is_trivially_true() -> None:
    body = client.get("/api/v1/core/cinematic/consistency").json()
    assert body == {
        "scenes": 0,
        "consistent": True,
        "grain": [],
        "lut": [],
        "palette": [],
        "findings": [],
    }


def test_the_cinematic_routes_contain_no_rules_of_their_own() -> None:
    """Routes expose data; the rules live in CinematicLibrary."""

    import inspect

    import app.main as main_module

    for name in (
        "cinematic_lenses",
        "cinematic_lenses_for",
        "cinematic_framing",
        "cinematic_lighting",
        "cinematic_motivations",
        "cinematic_motivation_of",
        "cinematic_audit",
        "cinematic_explain",
        "cinematic_consistency",
    ):
        body = inspect.getsource(getattr(main_module, name))
        for forbidden in ("TEAL_WORDS", "HIGHLIGHT_RISK", "MOTIVATIONS", "SUBTLE_GRAINS", "_check_"):
            assert forbidden not in body, f"{name} implements a rule inline ({forbidden})"


def test_the_openapi_surface_documents_the_cinematic_endpoints() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/v1/core/cinematic/lenses",
        "/api/v1/core/cinematic/lenses/for",
        "/api/v1/core/cinematic/framing",
        "/api/v1/core/cinematic/lighting",
        "/api/v1/core/cinematic/motivations",
        "/api/v1/core/cinematic/motivations/of",
        "/api/v1/core/cinematic/audit",
        "/api/v1/core/cinematic/explain",
        "/api/v1/core/cinematic/consistency",
    ):
        assert path in paths, path


def test_the_cinematic_routes_are_read_only() -> None:
    """A reference library is not mutated over HTTP."""

    spec = client.get("/openapi.json").json()["paths"]
    for path, methods in spec.items():
        if path.startswith("/api/v1/core/cinematic"):
            assert set(methods) == {"get"}, f"{path} exposes {sorted(methods)}"
