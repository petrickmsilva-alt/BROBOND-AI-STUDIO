"""ETAPA 17 — the documentation must match the code, or fail.

Documentation drift is not hypothetical in this repository. The audit for this
etapa found `README.md` claiming "pytest suite (176 tests)" while the suite had
1,040; `core/security.py` described as "at 0%" after ETAPA 16 moved it to 21%;
a "Current slice" section still calling the render "a local UI simulation" two
etapas after the fake render was removed; and a "Next implementation milestones"
list whose six items were all already built.

Every one of those was true when written and became false without anyone
noticing. These tests make that impossible: the numbers and claims below are
compared against the application in execution.
"""
from __future__ import annotations

import ast
import importlib.util
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

README = ROOT / "README.md"
ARCHITECTURE = ROOT / "ARCHITECTURE.md"
BACKEND_README = ROOT / "backend" / "README.md"
ROADMAP = ROOT / "ROADMAP.md"
API_DOC = ROOT / "docs" / "API.md"
LIMITATIONS = ROOT / "docs" / "LIMITATIONS.md"
ETAPAS_DOC = ROOT / "docs" / "ETAPAS.md"


def _read(path: pathlib.Path) -> str:
    assert path.is_file(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def inventory() -> dict:
    """The real route inventory, taken from the running application."""

    from fastapi.routing import APIRoute, APIWebSocketRoute

    from app.main import app

    http = [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/v1")]
    return {
        "http": http,
        "http_count": len(http),
        "core_count": len([r for r in http if r.path.startswith("/api/v1/core")]),
        "ws_count": len([r for r in app.routes if isinstance(r, APIWebSocketRoute)]),
        "tags": {sorted(r.tags)[0] for r in http if r.tags},
    }


@pytest.fixture(scope="module")
def test_count() -> int:
    """How many tests the suite actually collects, counted not remembered."""

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "backend/tests", "--collect-only", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": "backend"},
    )
    match = re.search(r"(\d+) tests? collected", proc.stdout)
    assert match, proc.stdout[-800:]
    return int(match.group(1))


# ---------------------------------------------------------------------------
# docs/API.md is generated — it must not drift
# ---------------------------------------------------------------------------


def test_the_api_doc_matches_the_application() -> None:
    """Regenerate in memory and compare. If a route changes, this fails."""

    spec = importlib.util.spec_from_file_location("gen_api_doc", ROOT / "scripts" / "gen_api_doc.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    expected = module.render()
    assert _read(API_DOC) == expected, (
        "docs/API.md is out of date — run "
        "`PYTHONPATH=backend python scripts/gen_api_doc.py > docs/API.md`"
    )


def test_every_documented_route_is_real(inventory) -> None:
    """Guards the other direction: a route in the doc that the app does not serve."""

    documented = set(re.findall(r"\| `(?:GET|POST|PUT|PATCH|DELETE)` \| `([^`]+)`", _read(API_DOC)))
    served = {r.path for r in inventory["http"]}
    assert documented <= served, sorted(documented - served)


def test_every_route_is_documented(inventory) -> None:
    documented = set(re.findall(r"\| `(?:GET|POST|PUT|PATCH|DELETE)` \| `([^`]+)`", _read(API_DOC)))
    served = {r.path for r in inventory["http"]}
    assert served <= documented, sorted(served - documented)


def test_the_api_doc_counts_are_right(inventory) -> None:
    text = _read(API_DOC)
    assert f"- **{inventory['http_count']}** rotas HTTP" in text
    assert f"- **{inventory['core_count']}** delas são `/api/v1/core/*`" in text
    assert f"- **{inventory['ws_count']}** WebSockets" in text
    assert f"- **{len(inventory['tags'])}** tags" in text


def test_the_generator_script_exists_and_is_runnable() -> None:
    """The doc tells the reader to run it, so it has to work."""

    script = ROOT / "scripts" / "gen_api_doc.py"
    assert script.is_file()
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": "backend"},
    )
    assert proc.returncode == 0, proc.stderr[-500:]
    assert proc.stdout.startswith("# BROBOND AI STUDIO — API")


# ---------------------------------------------------------------------------
# The headline numbers in the prose must match reality
# ---------------------------------------------------------------------------


def test_the_readme_states_the_real_test_count(test_count) -> None:
    text = _read(README)
    assert f"**{test_count:,} tests**" in text, f"README should say {test_count:,} tests"


def test_the_backend_readme_states_the_real_test_count(test_count) -> None:
    text = _read(BACKEND_README)
    assert f"# {test_count:,} tests" in text, f"backend/README should say {test_count:,} tests"


def test_the_readme_tree_comment_is_not_stale(test_count) -> None:
    """The directory tree said "176 tests" for eleven etapas."""

    text = _read(README)
    assert f"pytest suite ({test_count:,} tests)" in text


def _normalise(text: str) -> str:
    """The prose mixes English and Portuguese, so 1,075 and 1.075 both appear.

    Comparing thousands separators would make this test about punctuation rather
    than about whether the number is right.
    """

    return text.replace("\u00a0", " ").replace(".", ",")


def test_the_etapas_index_states_the_real_counts(inventory, test_count) -> None:
    text = _normalise(_read(ETAPAS_DOC))
    assert f"**{inventory['http_count']}**" in text
    assert f"**{inventory['core_count']}**" in text
    assert f"**{test_count:,}**" in text


# ---------------------------------------------------------------------------
# Claims that went stale once and must not go stale again
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stale",
    [
        "176 tests",                  # the count from an early etapa
        "local UI simulation",        # removed in ETAPA 15: the canvas shows the real render
        "Motion control preset browser",  # removed from the navigation in ETAPA 15
        "core/security.py` at 0%",    # ETAPA 16 moved it; the import attempt covers 21%
    ],
)
def test_the_readme_does_not_repeat_a_stale_claim(stale: str) -> None:
    assert stale not in _read(README)


def test_the_readme_milestones_are_not_a_todo_list_of_finished_work() -> None:
    """All six "next milestones" were already built by ETAPA 12.

    A milestone list that is entirely complete is not a plan, it is a lie about
    the state of the project. The section must either be gone or must not claim
    those items are pending.
    """

    text = _read(README)
    for finished in (
        "Add FastAPI service and typed OpenAPI client.",
        "Add Redis/Celery queue with GPU worker capability detection.",
        "Replace local UI simulation with WebSocket job updates",
    ):
        assert finished not in text, f"already delivered: {finished!r}"


def test_the_roadmap_no_longer_claims_publish_has_no_callers() -> None:
    """P0-3 was closed in ETAPA 11 by `publish_sync`."""

    assert "hub.publish` sem chamadores" not in _read(ROADMAP)


def test_the_roadmap_says_twelve_components_not_six() -> None:
    """It said "seis componentes" from ETAPA 2; there are twelve since ETAPA 14."""

    text = _read(ROADMAP)
    assert "seis componentes independentes" not in text


# ---------------------------------------------------------------------------
# The invariant the documentation claims about the Core
# ---------------------------------------------------------------------------


CORE_BANNED = {"fastapi", "starlette", "sqlalchemy", "celery", "boto3", "pydantic_settings"}

CORE_COMPONENTS = [
    "cinematic_library", "director_agent", "generation_spec_builder", "job_service",
    "memory_resolver", "persona_memory", "prompt_compiler", "quality", "shot_library",
    "shot_resolver", "storyboard_engine", "style_resolver", "timeline",
]


@pytest.mark.parametrize("component", CORE_COMPONENTS)
def test_every_core_component_is_framework_free(component: str) -> None:
    """Thirteen components, none importing a framework. Measured by AST.

    This is a weaker property than `INDEPENDENT_MODULES`, which also requires
    importing with no Core sibling. Six of the thirteen compose their
    siblings (or an injected interface) by design, so they satisfy this and
    not that — see docs/ETAPAS.md.
    """

    tree = ast.parse((ROOT / "backend" / "app" / "core" / f"{component}.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not (imported & CORE_BANNED), sorted(imported & CORE_BANNED)


def test_the_documentation_counts_thirteen_components() -> None:
    assert len(CORE_COMPONENTS) == 13
    assert "**13**" in _read(ETAPAS_DOC) or "**13**" in _read(ARCHITECTURE)


# ---------------------------------------------------------------------------
# Every report the index promises must exist
# ---------------------------------------------------------------------------


def test_every_report_named_in_the_index_exists() -> None:
    for name in re.findall(r"`((?:AUDIT|ETAPA\d+_REPORT)\.md)`", _read(ETAPAS_DOC)):
        assert (ROOT / name).is_file(), f"{name} is referenced but missing"


def test_every_existing_report_is_in_the_index() -> None:
    index = _read(ETAPAS_DOC)
    for report in sorted(ROOT.glob("ETAPA*_REPORT.md")) + [ROOT / "AUDIT.md"]:
        assert f"`{report.name}`" in index, f"{report.name} is not indexed"


# ---------------------------------------------------------------------------
# The limitations document states measured facts
# ---------------------------------------------------------------------------


def _identity_dependency(route) -> str | None:
    """Which identity dependency a route actually declares, if any.

    Counting routes that merely have a `user` parameter is not enough: a route
    on `Depends(optional_user)` accepts an anonymous caller. The limitations doc
    once said "10 de 58 rotas usam `Depends(current_user)`" while only 6 did —
    the other 4 were optional. The total was right and the claim was wrong, and
    a test that only checked the total let it through.
    """

    import inspect

    parameters = inspect.signature(route.endpoint).parameters
    if "user" not in parameters:
        return None
    dependency = getattr(parameters["user"].default, "dependency", None)
    return getattr(dependency, "__name__", None)


def test_the_authorisation_count_is_the_real_one(inventory) -> None:
    """76 of 114 routes touch identity — 73 require it, 3 do not (V4.0.1).

    PR002 closed the P0-2 exposure: 25 of 58 (22 required, 3 optional).
    PR003 added the six persona-profile routes, all `Depends(current_user)`;
    PR005 added a public planning route and PR007 added public provider health:
    31 of 66 (28 required, 3 optional). PR008 adds the six render routes, all
    `Depends(current_user)` (renders persist to the caller's workspace): 37
    of 72 (34 required, 3 optional). V3.1 adds the twelve Knowledge Graph
    routes, all `Depends(current_user)` (graph rows are tenant product data,
    like personas): 49 of 86 (46 required, 3 optional). V3.2 adds the thirteen
    continuity routes, all `Depends(current_user)` (locks and episodes are
    tenant product data, like personas): 62 of 99 (59 required, 3 optional).
    V3.3 adds the seven campaign routes, all `Depends(current_user)`
    (campaigns are tenant product data, like personas): 69 of 106 (66
    required, 3 optional). V3.4 adds the five quality routes: four are
    `Depends(current_user)` (reports badge tenant assets, like personas) and
    `/quality/config` is public reference data, like `/core/quality/rules`:
    73 of 111 (70 required, 3 optional). V4.0.1 (PR013) adds the three
    `/assets/library*` routes, all `Depends(current_user)` (the library is
    tenant product data, like personas): 76 of 114 (73 required, 3
    optional). Before PR002 the numbers were 10 (6 required, 4 optional). The
    prose and the guard move together, because the three numbers drift
    independently of each other. The three WebSockets are also authenticated,
    through the `token` query parameter (see test_security_authorization.py) —
    they are not routes, so they are not in the count.
    """

    kinds = [_identity_dependency(r) for r in inventory["http"]]
    required = len([k for k in kinds if k == "current_user"])
    optional = len([k for k in kinds if k == "optional_user"])
    touching = required + optional

    assert required == 75, f"rotas exigindo token mudaram: {required}"
    assert optional == 3, f"rotas com identidade opcional mudaram: {optional}"

    text = _read(LIMITATIONS)
    assert f"**{touching} de {inventory['http_count']} rotas**" in text
    assert f"**{required}** exigem token" in text
    assert f"**{optional}** aceitam token mas **não exigem**" in text


def test_the_anonymous_training_route_is_documented() -> None:
    """`/personas/{id}/train` accepts an anonymous caller. The doc must say so.

    This is the sharpest of the four optional routes: it starts a training run
    that can consume a GPU. It is a known open finding, not a fixed one, so the
    guard here is that it stays written down rather than that it disappears.
    """

    import inspect

    from app.main import app
    from fastapi.routing import APIRoute

    route = next(
        (r for r in app.routes if isinstance(r, APIRoute) and r.path == "/api/v1/personas/{persona_id}/train"),
        None,
    )
    assert route is not None, "a rota de treinamento sumiu; a doc fala dela"
    dependency = getattr(
        inspect.signature(route.endpoint).parameters["user"].default, "dependency", None
    )
    if getattr(dependency, "__name__", None) == "current_user":
        pytest.skip("a rota passou a exigir token; a limitacao foi fechada")

    assert "`/personas/{id}/train`" in _read(LIMITATIONS)


def test_the_dead_cluster_still_does_not_import() -> None:
    """Duplicated here on purpose: the limitations doc asserts it in prose.

    If this ever passes, the parallel backend came back and the doc is wrong.
    """

    with pytest.raises((ImportError, ModuleNotFoundError)):
        importlib.import_module("app.api.routes")


def test_the_dead_cluster_count_is_documented() -> None:
    text = _read(LIMITATIONS)
    assert "**100 statements**" in text
    for module in ("app/api/routes.py", "app/core/security.py", "app/services/generation.py", "app/api/dependencies.py"):
        assert module in text


def test_the_limitations_doc_names_the_absent_dependencies() -> None:
    """These are what make "it works" unclaimable, so they must stay visible."""

    text = _read(LIMITATIONS)
    for dependency in ("diffusers", "torch", "ffmpeg", "Pillow", "Redis", "MinIO"):
        assert dependency in text
