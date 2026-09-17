"""PR010.0 — Platform Freeze, ETAPA 5: no event may exist undocumented.

`docs/EVENT_CATALOG.md` is the official register of every event the platform
emits. This module holds it to the code in both directions:

* every event name declared in `app/events.py` and `app/render/progress.py`
  appears in the catalog;
* every event name the catalog documents exists in the code;
* the four names PR010.0 reserves for the AI Core are **not** emitted by
  anything, because the AI Core does not exist yet.

That last one is the part worth stating plainly. The PR names seven official
events; three are implemented, and reserving the other four is what stops the
AI Core from being born emitting `planCreated`, `plan.created` and
`PlanCreated` from three different places. A reserved name that quietly
acquires an emitter fails here.

Event names are wire contract: a client branches on `event`, so renaming one
breaks it silently. The catalog is how that stops being possible.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CATALOG = ROOT / "docs" / "EVENT_CATALOG.md"
EVENTS_MODULE = ROOT / "backend" / "app" / "events.py"
PROGRESS_MODULE = ROOT / "backend" / "app" / "render" / "progress.py"
APP = ROOT / "backend" / "app"

#: The seven names PR010.0 declares official, and how each maps onto the code.
#: `render_finished` is the domain name of an event whose wire name is
#: `batch_completed`; the wire name is not changed, because `lib/api.ts` and
#: `app/studio/render/page.tsx` already consume it.
OFFICIAL_EVENTS: dict[str, str | None] = {
    "request_received": None,
    "plan_created": None,
    "scene_started": "scene_started",
    "scene_completed": "scene_completed",
    "quality_finished": None,
    "render_finished": "batch_completed",
    "asset_created": None,
}

#: Reserved for the AI Core: documented, deliberately not emitted.
RESERVED = tuple(name for name, wire in OFFICIAL_EVENTS.items() if wire is None)

#: The job lifecycle vocabulary (`app/events.py`).
JOB_EVENT_NAMES = ("queued", "started", "progress", "complete", "failed", "cancelled")

#: The render vocabulary (`app/render/progress.py`).
RENDER_EVENT_NAMES = (
    "batch_started",
    "scene_started",
    "scene_progress",
    "scene_completed",
    "batch_completed",
)


def _catalog() -> str:
    assert CATALOG.is_file(), "PR010.0 ETAPA 5 requires docs/EVENT_CATALOG.md"
    return CATALOG.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The code's vocabulary is the catalog's vocabulary
# ---------------------------------------------------------------------------


def test_the_job_vocabulary_is_what_the_code_declares() -> None:
    from app.events import JOB_EVENTS

    assert JOB_EVENTS == JOB_EVENT_NAMES, "the job event tuple changed — update the catalog"


def test_the_render_vocabulary_is_what_the_code_declares() -> None:
    from app.render.progress import RENDER_EVENTS

    assert RENDER_EVENTS == RENDER_EVENT_NAMES, "the render event tuple changed — update the catalog"


@pytest.mark.parametrize("event", JOB_EVENT_NAMES)
def test_every_job_event_is_documented(event: str) -> None:
    assert f"`{event}`" in _catalog(), f"job event {event!r} is not in docs/EVENT_CATALOG.md"


@pytest.mark.parametrize("event", RENDER_EVENT_NAMES)
def test_every_render_event_is_documented(event: str) -> None:
    assert f"`{event}`" in _catalog(), f"render event {event!r} is not in docs/EVENT_CATALOG.md"


def test_no_undocumented_event_constant_exists() -> None:
    """Any `EVENT_* = "..."` in the tree must have its value in the catalog.

    This is the check that makes the rule real: adding a constant is how a new
    event gets born, and the catalog is where it has to be declared.
    """

    catalog = _catalog()
    undocumented: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            targets = []
            if isinstance(node, ast.Assign):
                targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets = [node.target.id]
            if not any(name.startswith("EVENT_") for name in targets):
                continue
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                if f"`{value.value}`" not in catalog:
                    undocumented.append(f"{path.relative_to(ROOT)}: {targets[0]} = {value.value!r}")
    assert not undocumented, "events missing from docs/EVENT_CATALOG.md:\n" + "\n".join(undocumented)


def test_every_event_the_catalog_names_exists_in_the_code() -> None:
    """The other direction: the catalog must not document a fiction.

    Only the backtick-quoted names inside the two vocabulary tables are
    considered, so prose may still discuss a name without declaring it.
    """

    from app.events import JOB_EVENTS
    from app.render.progress import RENDER_EVENTS

    known = set(JOB_EVENTS) | set(RENDER_EVENTS) | set(OFFICIAL_EVENTS)
    catalog = _catalog()
    section = catalog.split("## 4. Vocabulário reservado")[0]
    documented = {
        name
        for name in re.findall(r"^\| `([a-z_]+)` \|", section, re.M)
        if name not in {"status", "event", "error", "progress_"}
    }
    unknown = sorted(documented - known)
    assert not unknown, f"the catalog documents events that do not exist: {unknown}"


# ---------------------------------------------------------------------------
# The seven official names of PR010.0
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("event", sorted(OFFICIAL_EVENTS))
def test_every_official_event_is_in_the_catalog(event: str) -> None:
    """All seven names PR010.0 lists must be registered, implemented or not."""

    assert f"`{event}`" in _catalog(), f"official event {event!r} is not registered"


def test_the_implemented_official_events_really_are_emitted() -> None:
    """`scene_started`, `scene_completed` and `render_finished`/`batch_completed`."""

    from app.render.progress import RENDER_EVENTS

    for official, wire in OFFICIAL_EVENTS.items():
        if wire is None:
            continue
        assert wire in RENDER_EVENTS, f"{official} maps to {wire}, which is not a real event"


def test_render_finished_is_the_terminal_render_event() -> None:
    """The domain name the PR uses is the wire name the clients already consume."""

    from app.render.progress import TERMINAL_RENDER_EVENT

    assert TERMINAL_RENDER_EVENT == OFFICIAL_EVENTS["render_finished"] == "batch_completed"


def test_the_catalog_records_the_render_finished_alias() -> None:
    """A reader must be able to find `batch_completed` from `render_finished`."""

    catalog = _catalog()
    assert "render_finished" in catalog
    assert "batch_completed" in catalog
    assert re.search(r"`render_finished`.*`batch_completed`", catalog, re.S)


@pytest.mark.parametrize("event", RESERVED)
def test_a_reserved_event_is_not_emitted_by_anything(event: str) -> None:
    """The AI Core's vocabulary is reserved, not implemented.

    PR010.0 is a stabilisation PR: zero functional change. If one of these
    names acquires an emitter, that is a feature arriving through a freeze, and
    it fails here until the catalog defines its payload.
    """

    offenders: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if f'"{event}"' in text or f"'{event}'" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"{event} is reserved for the AI Core but appears in: {offenders}"


@pytest.mark.parametrize("event", RESERVED)
def test_a_reserved_event_is_declared_as_reserved(event: str) -> None:
    """Reserved names live in their own section, so nobody reads them as live."""

    reserved_section = _catalog().split("## 4. Vocabulário reservado")[-1]
    assert f"`{event}`" in reserved_section, f"{event} must be listed under reserved vocabulary"


# ---------------------------------------------------------------------------
# Honesty: the catalog states what is NOT emitted
# ---------------------------------------------------------------------------


def test_the_catalog_admits_that_queued_has_no_emitter() -> None:
    """`EVENT_QUEUED` is declared and imported, but nothing emits it.

    Measured, not assumed: the constant is imported by `queue.py` and never
    passed to `transition()`. A catalog that implied otherwise would be a
    documented promise the system does not keep.
    """

    source = (ROOT / "backend" / "app" / "queue.py").read_text(encoding="utf-8")
    emitted = re.findall(r"event=(EVENT_\w+)", source)
    assert "EVENT_QUEUED" not in emitted, "queued now has an emitter — update the catalog"

    catalog = _catalog()
    row = next((line for line in catalog.splitlines() if line.startswith("| `queued`")), "")
    assert "**Não**" in row, "the catalog must state that `queued` is not emitted today"


def test_the_catalog_documents_the_status_versus_event_distinction() -> None:
    """`complete` (event) vs `completed` (status) is the easiest thing to get wrong."""

    from app.events import external_status

    assert external_status("complete") == "completed"
    assert external_status("failed") == "failed"

    catalog = _catalog()
    assert "external_status" in catalog
    assert "`completed`" in catalog


def test_the_catalog_documents_the_in_process_limitation() -> None:
    """The hub is in-process; a Celery worker's events do not reach the API's sockets."""

    catalog = _catalog()
    assert "in-process" in catalog
    assert "publish_sync" in catalog


def test_the_catalog_covers_the_training_socket() -> None:
    """The one channel with no named events must still be registered."""

    assert "/api/v1/personas/{persona_id}/training/events/{run_id}" in _catalog()


# ---------------------------------------------------------------------------
# Payload contracts
# ---------------------------------------------------------------------------


def test_the_job_payload_has_the_documented_keys() -> None:
    from app.events import job_event

    payload = job_event("job-1", status="running", progress=55, event="progress")
    assert set(payload) == {"job_id", "event", "status", "progress", "at"}

    full = job_event("job-1", status="complete", progress=100, event="complete", output_url="u", error="e")
    assert set(full) == {"job_id", "event", "status", "progress", "at", "output_url", "error"}
    assert full["status"] == "completed", "the wire says completed, the internal state says complete"


def test_the_render_payload_has_the_documented_keys() -> None:
    from app.render.progress import render_event

    payload = render_event("b-1", "batch_started")
    assert set(payload) == {"batch_id", "event", "at"}

    full = render_event(
        "b-1",
        "scene_completed",
        scene_id="s-1",
        scene_number=1,
        status="completed",
        progress=100,
        eta_seconds=0.0,
        error=None,
        asset={"object_key": "k"},
        job={"status": "complete"},
    )
    assert {"batch_id", "event", "at", "scene_id", "scene_number", "status", "progress", "asset", "job"} <= set(full)


def test_an_unknown_render_event_is_refused_at_runtime() -> None:
    """The vocabulary is enforced by the code, not only by this test."""

    from app.render.progress import render_event

    with pytest.raises(ValueError, match="unknown render event"):
        render_event("b-1", "plan_created")


def test_the_terminal_job_statuses_are_the_documented_three() -> None:
    from app.events import TERMINAL_STATUSES

    assert TERMINAL_STATUSES == frozenset({"complete", "failed", "cancelled"})
