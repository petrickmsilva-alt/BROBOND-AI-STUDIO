"""V3.2 — ContinuityRepository: workspace-scoped persistence over the real tables.

Every test owns a fresh ``ws-<uuid>`` workspace against the shared test
database (the same isolation the graph/persona suites use): cross-workspace
reads behave as 404s, episode numbers collide only within a tenant, and the
fallback chain (episode → campaign default → persona-global default) is
pinned here at the persistence boundary. The HTTP mapping (404/409/422)
lives in `test_continuity_api.py`.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.continuity import (
    DEFAULT_CAMPAIGN,
    DEFAULT_EPISODE,
    LOCK_TYPES,
    ContinuityRepositoryError,
    ContinuityValidationError,
    continuity_repo,
    continuity_store_for,
    dumps_payload,
    loads_payload,
    normalize_lock_type,
    utcnow,
)
from app.continuity.continuity_models import ContinuityEpisode, ContinuityLock
from app.continuity.continuity_repository import _fallback_chain, episode_view, lock_view


@pytest.fixture()
def ws() -> str:
    return f"ws-{uuid4().hex}"


def _upsert(workspace_id: str, lock_type: str = "wardrobe", **kwargs):
    payload = {"outfit": "black blazer", **kwargs.pop("payload", {})}
    return continuity_repo.upsert_lock(
        workspace_id,
        lock_type=lock_type,
        persona_id=kwargs.pop("persona_id", "CHAR_PETRICK"),
        campaign_id=kwargs.pop("campaign_id", "legacy"),
        episode=kwargs.pop("episode", None),
        payload=payload,
        fingerprint=kwargs.pop("fingerprint", "a1b2c3d4e5f60718"),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Vocabulary + JSON helpers (continuity_models)
# ---------------------------------------------------------------------------


def test_lock_types_are_the_five_sprint_locks() -> None:
    assert LOCK_TYPES == ("identity", "wardrobe", "location", "vehicle", "voice")
    assert DEFAULT_CAMPAIGN == "default"
    assert DEFAULT_EPISODE == 0


@pytest.mark.parametrize("kind", ["identity", "wardrobe", "location", "vehicle", "voice"])
def test_normalize_lock_type_accepts_the_vocabulary(kind: str) -> None:
    assert normalize_lock_type(f"  {kind.upper()} ") == kind


@pytest.mark.parametrize("bad", ["", "  ", "starship", "prop", None, 123, ["wardrobe"]])
def test_normalize_lock_type_refuses_anything_else(bad) -> None:
    with pytest.raises(ContinuityValidationError, match="unknown lock type"):
        normalize_lock_type(bad)


def test_dumps_and_loads_payload_round_trip() -> None:
    raw = dumps_payload({"outfit": "blazer", "nested": {"a": [1, 2]}})
    assert loads_payload(raw) == {"outfit": "blazer", "nested": {"a": [1, 2]}}


def test_dumps_payload_refuses_non_objects_and_non_json() -> None:
    with pytest.raises(ContinuityValidationError, match="must be an object"):
        dumps_payload(["x"])  # type: ignore[arg-type]
    with pytest.raises(ContinuityValidationError, match="not JSON-serialisable"):
        dumps_payload({"x": object()})


@pytest.mark.parametrize("raw", [None, "", "{not json", "[1, 2]", "5", '"s"'])
def test_loads_payload_reads_corrupt_rows_as_empty(raw) -> None:
    assert loads_payload(raw) == {}


def test_utcnow_returns_a_naive_utc_datetime() -> None:
    stamp = utcnow()
    assert stamp.tzinfo is None


# ---------------------------------------------------------------------------
# Lock upsert + reads
# ---------------------------------------------------------------------------


def test_upsert_and_read_back(ws: str) -> None:
    view = _upsert(ws, episode=2, fingerprint="f" * 16)
    assert view.lock_type == "wardrobe"
    assert (view.persona_id, view.campaign_id, view.episode) == ("CHAR_PETRICK", "legacy", 2)
    assert view.payload == {"outfit": "black blazer"}
    assert view.fingerprint == "f" * 16
    assert view.version == 1
    assert view.created_at and view.updated_at

    same = continuity_repo.get_lock(ws, "wardrobe", "CHAR_PETRICK", "legacy", 2)
    assert same == view


def test_upsert_normalises_keys(ws: str) -> None:
    view = _upsert(ws, lock_type=" Wardrobe ", persona_id="  CHAR_PETRICK ", campaign_id="  legacy ")
    assert (view.lock_type, view.persona_id, view.campaign_id, view.episode) == (
        "wardrobe",
        "CHAR_PETRICK",
        "legacy",
        None,
    )


def test_upsert_of_the_same_scope_replaces_and_bumps_version(ws: str) -> None:
    first = _upsert(ws, payload={"outfit": "black blazer"}, fingerprint="a" * 16)
    second = _upsert(ws, payload={"outfit": "white t-shirt"}, fingerprint="b" * 16)
    assert second.version == first.version + 1
    assert second.payload == {"outfit": "white t-shirt"}
    assert second.fingerprint == "b" * 16


def test_episode_scopes_do_not_clobber_each_other(ws: str) -> None:
    _upsert(ws, episode=None, payload={"outfit": "default"}, fingerprint="a" * 16)
    _upsert(ws, episode=3, payload={"outfit": "override"}, fingerprint="b" * 16)
    default = continuity_repo.get_lock(ws, "wardrobe", "CHAR_PETRICK", "legacy", None)
    override = continuity_repo.get_lock(ws, "wardrobe", "CHAR_PETRICK", "legacy", 3)
    assert default is not None and default.payload == {"outfit": "default"}
    assert override is not None and override.payload == {"outfit": "override"}


@pytest.mark.parametrize("bad", ["starship", "", None])
def test_upsert_refuses_unknown_lock_types(ws: str, bad) -> None:
    with pytest.raises(ContinuityValidationError):
        _upsert(ws, lock_type=bad)


def test_upsert_validates_persona_campaign_episode_and_fingerprint(ws: str) -> None:
    with pytest.raises(ContinuityValidationError):
        _upsert(ws, persona_id="  ")
    with pytest.raises(ContinuityValidationError):
        _upsert(ws, campaign_id=123)  # type: ignore[arg-type]
    with pytest.raises(ContinuityValidationError):
        _upsert(ws, episode=0)
    with pytest.raises(ContinuityValidationError):
        continuity_repo.upsert_lock(
            ws, lock_type="wardrobe", persona_id="CHAR_PETRICK", payload=["x"], fingerprint="a" * 16  # type: ignore[arg-type]
        )
    with pytest.raises(ContinuityValidationError, match="fingerprint must not be blank"):
        _upsert(ws, fingerprint="  ")
    with pytest.raises(ContinuityValidationError, match="fingerprint must not be blank"):
        _upsert(ws, fingerprint=123)  # type: ignore[arg-type]


def test_upsert_defaults_campaign_and_payload(ws: str) -> None:
    view = continuity_repo.upsert_lock(
        ws, lock_type="voice", persona_id="CHAR_PETRICK", payload=None, fingerprint="c" * 16
    )
    assert (view.campaign_id, view.episode, view.payload) == ("default", None, {})


def test_get_lock_validates_before_reading(ws: str) -> None:
    with pytest.raises(ContinuityValidationError):
        continuity_repo.get_lock(ws, "starship", "CHAR_PETRICK")
    with pytest.raises(ContinuityValidationError):
        continuity_repo.get_lock(ws, "wardrobe", "  ")
    with pytest.raises(ContinuityValidationError):
        continuity_repo.get_lock(ws, "wardrobe", "CHAR_PETRICK", "legacy", 0)


def test_get_lock_returns_none_when_nothing_is_locked(ws: str) -> None:
    assert continuity_repo.get_lock(ws, "wardrobe", "CHAR_PETRICK", "legacy", 7) is None


def test_locks_do_not_leak_across_workspaces(ws: str) -> None:
    _upsert(ws)
    assert continuity_repo.get_lock(f"ws-{uuid4().hex}", "wardrobe", "CHAR_PETRICK", "legacy", 1) is None


# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------


def test_fallback_chain_orders_scopes_most_specific_first() -> None:
    assert _fallback_chain("legacy", 3) == [("legacy", 3), ("legacy", 0), ("default", 0)]
    assert _fallback_chain("legacy", None) == [("legacy", 0), ("default", 0)]
    assert _fallback_chain("default", 3) == [("default", 3), ("default", 0)]
    assert _fallback_chain("default", None) == [("default", 0)]


def test_get_lock_prefers_the_episode_override(ws: str) -> None:
    _upsert(ws, campaign_id="legacy", episode=None, payload={"outfit": "default"}, fingerprint="a" * 16)
    _upsert(ws, campaign_id="legacy", episode=2, payload={"outfit": "override"}, fingerprint="b" * 16)
    view = continuity_repo.get_lock(ws, "wardrobe", "CHAR_PETRICK", "legacy", 2)
    assert view is not None and view.payload == {"outfit": "override"}


def test_get_lock_falls_back_to_the_campaign_default(ws: str) -> None:
    _upsert(ws, campaign_id="legacy", episode=None, payload={"outfit": "default"}, fingerprint="a" * 16)
    view = continuity_repo.get_lock(ws, "wardrobe", "CHAR_PETRICK", "legacy", 9)
    assert view is not None and view.episode is None
    assert view.payload == {"outfit": "default"}


def test_get_lock_falls_back_to_the_persona_global_default(ws: str) -> None:
    continuity_repo.upsert_lock(
        ws,
        lock_type="identity",
        persona_id="CHAR_PETRICK",
        campaign_id="default",
        payload={"face": "oval face"},
        fingerprint="d" * 16,
    )
    view = continuity_repo.get_lock(ws, "identity", "CHAR_PETRICK", "any-campaign", 4)
    assert view is not None and view.campaign_id == "default"
    assert view.payload == {"face": "oval face"}


def test_list_locks_filters_and_orders_stably(ws: str) -> None:
    _upsert(ws, lock_type="voice", persona_id="CHAR_B", campaign_id="legacy")
    _upsert(ws, lock_type="wardrobe", persona_id="CHAR_A", campaign_id="legacy", episode=2)
    _upsert(ws, lock_type="wardrobe", persona_id="CHAR_A", campaign_id="legacy")
    views = continuity_repo.list_locks(ws)
    assert [(view.persona_id, view.episode, view.lock_type) for view in views] == [
        ("CHAR_A", None, "wardrobe"),
        ("CHAR_A", 2, "wardrobe"),
        ("CHAR_B", None, "voice"),
    ]
    assert [view.persona_id for view in continuity_repo.list_locks(ws, persona_id="CHAR_B")] == ["CHAR_B"]
    assert len(continuity_repo.list_locks(ws, campaign_id="legacy")) == 3
    assert continuity_repo.list_locks(ws, persona_id="CHAR_B", campaign_id="other") == []
    assert continuity_repo.list_locks(f"ws-{uuid4().hex}") == []
    assert views[0].to_dict()["lock_type"] == "wardrobe"


# ---------------------------------------------------------------------------
# Episodes
# ---------------------------------------------------------------------------


def _episode(workspace_id: str, **kwargs):
    return continuity_repo.create_episode(
        workspace_id,
        persona_id=kwargs.pop("persona_id", "CHAR_PETRICK"),
        campaign_id=kwargs.pop("campaign_id", "legacy"),
        episode=kwargs.pop("episode", 1),
        title=kwargs.pop("title", "Pilot"),
        notes=kwargs.pop("notes", ""),
        snapshot=kwargs.pop("snapshot", {"consistent": True}),
        **kwargs,
    )


def test_create_and_read_back_an_episode(ws: str) -> None:
    view = _episode(ws, episode=2, title="  Second ", notes=" night shoot ")
    assert view.workspace_id == ws
    assert (view.persona_id, view.campaign_id, view.episode) == ("CHAR_PETRICK", "legacy", 2)
    assert (view.title, view.notes) == ("Second", "night shoot")
    assert view.snapshot == {"consistent": True}
    assert view.id and view.created_at

    same = continuity_repo.get_episode(ws, "CHAR_PETRICK", "legacy", 2)
    assert same == view
    assert same is not None and same.to_dict()["title"] == "Second"


def test_create_episode_conflicts_on_taken_numbers(ws: str) -> None:
    _episode(ws, episode=1)
    with pytest.raises(ContinuityRepositoryError, match="already exists"):
        _episode(ws, episode=1)


def test_episode_numbers_collide_only_within_a_tenant_scope(ws: str) -> None:
    _episode(ws, episode=1)
    _episode(ws, persona_id="CHAR_OTHER", episode=1)
    _episode(ws, campaign_id="other", episode=1)
    other_ws = f"ws-{uuid4().hex}"
    _episode(other_ws, episode=1)
    assert len(continuity_repo.list_episodes(ws)) == 3


def test_create_episode_validates_everything(ws: str) -> None:
    with pytest.raises(ContinuityValidationError):
        _episode(ws, persona_id="  ")
    with pytest.raises(ContinuityValidationError):
        _episode(ws, campaign_id=123)  # type: ignore[arg-type]
    with pytest.raises(ContinuityValidationError):
        _episode(ws, episode=0)
    with pytest.raises(ContinuityValidationError, match="episode number is required"):
        _episode(ws, episode=None)
    with pytest.raises(ContinuityValidationError, match="title and notes must be strings"):
        _episode(ws, title=123)  # type: ignore[arg-type]
    with pytest.raises(ContinuityValidationError, match="title and notes must be strings"):
        _episode(ws, notes=["x"])  # type: ignore[arg-type]


def test_next_episode_number_counts_from_one(ws: str) -> None:
    assert continuity_repo.next_episode_number(ws, "CHAR_PETRICK", "legacy") == 1
    _episode(ws, episode=1)
    _episode(ws, episode=2)
    assert continuity_repo.next_episode_number(ws, "CHAR_PETRICK", "legacy") == 3
    assert continuity_repo.next_episode_number(ws, "CHAR_PETRICK", "other") == 1


def test_get_episode_misses_read_as_none(ws: str) -> None:
    assert continuity_repo.get_episode(ws, "CHAR_PETRICK", "legacy", 9) is None
    assert continuity_repo.get_episode(ws, "CHAR_PETRICK", "legacy", None) is None  # type: ignore[arg-type]
    _episode(ws, episode=1)
    assert continuity_repo.get_episode(f"ws-{uuid4().hex}", "CHAR_PETRICK", "legacy", 1) is None


def test_list_episodes_filters_and_orders_oldest_first(ws: str) -> None:
    _episode(ws, persona_id="CHAR_B", episode=2)
    _episode(ws, persona_id="CHAR_B", episode=1)
    _episode(ws, persona_id="CHAR_A", campaign_id="other", episode=1)
    views = continuity_repo.list_episodes(ws)
    assert [(view.persona_id, view.campaign_id, view.episode) for view in views] == [
        ("CHAR_A", "other", 1),
        ("CHAR_B", "legacy", 1),
        ("CHAR_B", "legacy", 2),
    ]
    assert len(continuity_repo.list_episodes(ws, persona_id="CHAR_B")) == 2
    assert len(continuity_repo.list_episodes(ws, campaign_id="other")) == 1
    assert continuity_repo.list_episodes(ws, persona_id="CHAR_B", campaign_id="other") == []
    assert continuity_repo.list_episodes(f"ws-{uuid4().hex}") == []


# ---------------------------------------------------------------------------
# Views + store adapter
# ---------------------------------------------------------------------------


def test_lock_and_episode_views_map_rows() -> None:
    lock_row = ContinuityLock(
        workspace_id="ws",
        persona_id="P",
        campaign_id="C",
        episode=0,
        lock_type="voice",
        payload_json='{"voice_profile": "v"}',
        fingerprint="e" * 16,
        version=2,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    lock = lock_view(lock_row)
    assert (lock.episode, lock.version, lock.payload) == (None, 2, {"voice_profile": "v"})

    episode_row = ContinuityEpisode(
        workspace_id="ws",
        persona_id="P",
        campaign_id="C",
        episode=1,
        title="T",
        notes="N",
        snapshot_json='{"consistent": false}',
        created_at=utcnow(),
    )
    episode_row.id = "ep-1"
    episode = episode_view(episode_row)
    assert (episode.id, episode.snapshot) == ("ep-1", {"consistent": False})


def test_continuity_store_for_binds_the_resolver_to_one_workspace(ws: str) -> None:
    _upsert(ws, payload={"outfit": "mine"}, fingerprint="a" * 16)
    store = continuity_store_for(ws)
    view = store.get_lock("wardrobe", "CHAR_PETRICK", "legacy", 1)
    assert view is not None and view.payload == {"outfit": "mine"}
    assert continuity_store_for(f"ws-{uuid4().hex}").get_lock("wardrobe", "CHAR_PETRICK", "legacy", 1) is None
