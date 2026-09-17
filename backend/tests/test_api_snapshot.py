"""PR010.0 — Platform Freeze, ETAPA 3: the public surface cannot move quietly.

`docs/API_SNAPSHOT.json` is the frozen public contract of the platform: every
HTTP route, every WebSocket, every public model, with its auth requirement and
its field types. It is generated from the running application by
`scripts/gen_api_snapshot.py`.

This module regenerates the snapshot in memory and compares it to the committed
file. The two can only disagree if the application changed, so the failure is
never mysterious — and the fix is never "edit the JSON":

    PYTHONPATH=backend python scripts/gen_api_snapshot.py > docs/API_SNAPSHOT.json

That is the whole mechanism. Changing the public API stops being a side effect
of an unrelated edit and becomes an explicit, reviewable diff — which is what
"mudança exige atualização explícita" means in practice.

Why this exists alongside `test_docs_accuracy.py`
-------------------------------------------------
`docs/API.md` is prose for a human: paths, tags, one-line descriptions. It does
not record field types, nullability or which routes require a token, so a
response model could lose a field, or a route could quietly become public, with
`API.md` still perfectly accurate. This snapshot closes that gap.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "docs" / "API_SNAPSHOT.json"
GENERATOR = ROOT / "scripts" / "gen_api_snapshot.py"

REGENERATE = (
    "docs/API_SNAPSHOT.json is out of date — run "
    "`PYTHONPATH=backend python scripts/gen_api_snapshot.py > docs/API_SNAPSHOT.json` "
    "and review the diff: it is a change to the public contract."
)


@pytest.fixture(scope="module")
def generator():
    spec = importlib.util.spec_from_file_location("gen_api_snapshot", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def committed() -> dict:
    assert SNAPSHOT.is_file(), "PR010.0 ETAPA 3 requires docs/API_SNAPSHOT.json"
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def live(generator) -> dict:
    return generator.build()


# ---------------------------------------------------------------------------
# The snapshot is the application
# ---------------------------------------------------------------------------


def test_the_snapshot_file_is_exactly_what_the_generator_produces(generator) -> None:
    """Byte-for-byte, so formatting drift cannot hide a contract change."""

    assert SNAPSHOT.read_text(encoding="utf-8") == generator.render(), REGENERATE


def test_the_generator_is_deterministic(generator) -> None:
    """Two runs must agree, or every unrelated PR would show a diff here."""

    assert generator.render() == generator.render()


def test_every_live_route_is_in_the_snapshot(committed, live) -> None:
    """A new route must be declared before it can ship."""

    recorded = {(entry["path"], tuple(entry["methods"])) for entry in committed["http"]}
    serving = {(entry["path"], tuple(entry["methods"])) for entry in live["http"]}
    assert serving <= recorded, f"undeclared routes: {sorted(serving - recorded)}. {REGENERATE}"


def test_every_snapshot_route_is_still_served(committed, live) -> None:
    """The other direction: a removed route is a breaking change, not a tidy-up."""

    recorded = {(entry["path"], tuple(entry["methods"])) for entry in committed["http"]}
    serving = {(entry["path"], tuple(entry["methods"])) for entry in live["http"]}
    assert recorded <= serving, f"routes vanished: {sorted(recorded - serving)}. {REGENERATE}"


def test_every_websocket_is_recorded(committed, live) -> None:
    assert committed["websockets"] == live["websockets"], REGENERATE


def test_every_public_model_is_recorded(committed, live) -> None:
    assert set(committed["models"]) == set(live["models"]), REGENERATE


def test_no_model_field_changed_shape(committed, live) -> None:
    """Field-level comparison, so a renamed or re-typed field is caught.

    This is the check `docs/API.md` structurally cannot do: the prose inventory
    records paths, not payloads, so a response model could lose `output_url`
    and the documentation would stay true.
    """

    differences = []
    for name, model in sorted(committed["models"].items()):
        current = live["models"].get(name)
        if current is None:
            differences.append(f"{name}: removed")
        elif current != model:
            differences.append(f"{name}: {model} != {current}")
    assert not differences, "public models changed:\n" + "\n".join(differences) + f"\n{REGENERATE}"


# ---------------------------------------------------------------------------
# Authentication is part of the contract
# ---------------------------------------------------------------------------


def test_no_route_silently_dropped_its_authentication(committed, live) -> None:
    """A protected route becoming public is a security regression.

    It is also exactly the kind of change that a diff of `main.py` makes easy to
    miss, because it looks like one deleted `Depends(...)`.
    """

    by_path = {(e["path"], tuple(e["methods"])): e for e in live["http"]}
    downgrades = []
    for entry in committed["http"]:
        current = by_path.get((entry["path"], tuple(entry["methods"])))
        if current is None:
            continue
        if entry["auth"] == "required" and current["auth"] != "required":
            downgrades.append(f"{entry['path']} {entry['methods']}: required -> {current['auth']}")
        if entry["auth"] == "optional" and current["auth"] == "public":
            downgrades.append(f"{entry['path']} {entry['methods']}: optional -> public")
    assert not downgrades, "authentication weakened:\n" + "\n".join(downgrades)


def test_the_websockets_still_authenticate(committed) -> None:
    """All three sockets authenticate through `?token=` (PR002)."""

    assert [socket["auth"] for socket in committed["websockets"]] == ["token", "token", "token"]


def test_the_authentication_split_matches_the_documented_one(committed) -> None:
    """70 required / 3 optional / 38 public — the numbers `docs/LIMITATIONS.md`
    and `test_docs_accuracy.py` already hold the line on, now also frozen here."""

    summary = committed["summary"]
    assert summary["auth_required"] == 70
    assert summary["auth_optional"] == 3
    assert summary["auth_public"] == 38
    assert summary["auth_required"] + summary["auth_optional"] + summary["auth_public"] == summary["http_routes"]


# ---------------------------------------------------------------------------
# The snapshot agrees with the rest of the documentation
# ---------------------------------------------------------------------------


def test_the_summary_counts_match_the_recorded_entries(committed) -> None:
    """The headline numbers are derived, so they cannot be edited by hand."""

    summary = committed["summary"]
    assert summary["http_routes"] == len(committed["http"])
    assert summary["websockets"] == len(committed["websockets"])
    assert summary["models"] == len(committed["models"])
    assert summary["core_routes"] == len([e for e in committed["http"] if e["path"].startswith("/api/v1/core")])


def test_the_snapshot_and_the_api_doc_describe_the_same_surface(committed) -> None:
    """`docs/API.md` and this file are generated from one application."""

    import re

    text = (ROOT / "docs" / "API.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"\| `(?:GET|POST|PUT|PATCH|DELETE)[^`]*` \| `([^`]+)`", text))
    recorded = {entry["path"] for entry in committed["http"]}
    assert documented == recorded, sorted(documented ^ recorded)


def test_the_snapshot_declares_how_to_regenerate_itself(committed) -> None:
    """Someone hitting the failure must find the fix in the file."""

    assert "gen_api_snapshot.py" in committed["_comment"]
    assert committed["generator"] == "scripts/gen_api_snapshot.py"


def test_the_snapshot_version_is_declared(committed, generator) -> None:
    assert committed["snapshot_version"] == generator.SNAPSHOT_VERSION


# ---------------------------------------------------------------------------
# The guard must be able to fail
# ---------------------------------------------------------------------------


def test_a_changed_model_is_detected(committed, live) -> None:
    """Negative control: mutate a field type and the comparison must object.

    Without this, a bug in the diffing logic would leave every assertion above
    passing for the wrong reason.
    """

    import copy

    tampered = copy.deepcopy(committed)
    tampered["models"]["JobResponse"]["fields"]["progress"] = "string"

    assert tampered["models"]["JobResponse"] != live["models"]["JobResponse"]
    assert committed["models"]["JobResponse"] == live["models"]["JobResponse"]


def test_a_removed_route_is_detected(committed, live) -> None:
    """Negative control for the route comparison."""

    recorded = {(e["path"], tuple(e["methods"])) for e in committed["http"]}
    serving = {(e["path"], tuple(e["methods"])) for e in live["http"]}
    shrunk = serving - {next(iter(serving))}
    assert not recorded <= shrunk, "the comparison would not notice a deleted route"
