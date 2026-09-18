"""PR010.0 — Platform Freeze, ETAPA 2: the architecture is enforced, not described.

`docs/ARCHITECTURE_MANIFEST.md` declares who owns what and who may import whom.
This module turns that declaration into a build failure. It parses every file
under `backend/app/`, classifies it into a module, builds the real import graph
and compares it against the manifest.

The four boundaries the PR names explicitly:

    Director  -/->  Providers      planning must not depend on hardware
    Quality   -/->  Render         a verdict must not be able to execute
    Providers -/->  Director       execution must not interpret intention
    Campaign  -/->  Quality        a plan must not be edited by a score

and the asymmetric one that guards a module which does not exist yet:

    *         -/->  AI Core        the orchestrator calls; it is not called

All five already hold in the code as committed. That is the point of a freeze:
these tests do not fix a violation, they make the current shape permanent. To
prove they are not vacuous, `test_the_guard_detects_a_planted_violation`
injects a forbidden import into a copy of the tree and asserts the guard turns
red.

Why the whole tree is classified
--------------------------------
An allow-list with holes is not an allow-list. If a file belonged to no module,
a new coupling could be introduced through it and the guard would shrug. So
`test_every_backend_file_has_an_owner` fails on any unclassified file, which
also means a brand-new package must be declared in the manifest before it can
be merged.

Transitivity
------------
A forbidden edge is forbidden through intermediaries too, otherwise the rule is
trivially defeated by adding a pass-through module. `_path_between` walks the
closure, and the failure message names the actual path, so a violation is
debuggable rather than just reported.
"""
from __future__ import annotations

import ast
import pathlib
import re
import shutil
import subprocess
import sys
from collections import defaultdict, deque

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"
MANIFEST = ROOT / "docs" / "ARCHITECTURE_MANIFEST.md"


# ---------------------------------------------------------------------------
# The declared architecture. Mirrors docs/ARCHITECTURE_MANIFEST.md, and
# `test_the_manifest_declares_every_module` proves the two agree.
# ---------------------------------------------------------------------------

#: Module name -> the Python packages that implement it. Longest prefix wins,
#: so `app.core.quality` can belong to Quality Engine while `app.core` belongs
#: to Package Root.
MODULES: dict[str, tuple[str, ...]] = {
    "AI Core": ("app.ai_core",),
    "Director AI": ("app.core.director", "app.core.director_agent"),
    "Storyboard Engine": ("app.core.storyboard_engine", "app.core.timeline"),
    "Render Engine": ("app.render",),
    "Provider Registry": ("app.providers",),
    "Campaign Builder": ("app.campaign",),
    "Quality Engine": ("app.quality", "app.core.quality"),
    "Persona Engine": (
        "app.core.persona_memory",
        "app.core.memory_resolver",
        "app.repositories.persona_repository",
    ),
    "Database Guard": ("app.core.database_guard",),
    "Contracts": ("app.contracts", "app.core.contracts"),
    "Prompt Compiler": ("app.core.prompt_compiler", "app.prompt_engine"),
    "Cinematic Knowledge": (
        "app.core.cinematic_library",
        "app.core.shot_library",
        "app.core.shot_resolver",
        "app.core.style_resolver",
        "app.knowledge",
        "app.conditioning",
    ),
    "Spec Builder": ("app.core.generation_spec_builder", "app.spec_adapter"),
    "Job Queue": (
        "app.core.job_service",
        "app.job_service",
        "app.jobs",
        "app.store",
        "app.queue",
        "app.events",
        "app.repositories",
    ),
    "Continuity Engine": ("app.continuity",),
    "Knowledge Graph": ("app.graph",),
    "Storage": ("app.storage", "app.media", "app.preprocessing", "app.training", "app.lora"),
    "Persistence": ("app.db", "app.models"),
    "Security": ("app.auth", "app.audit"),
    "Runtime Config": ("app.core.config", "app.system", "app.readiness"),
    "Application Boundary": ("app.main", "app.schemas", "app.provider_capabilities"),
    "Dead Cluster": ("app.api", "app.services", "app.core.security"),
    "Package Root": ("app", "app.core"),
}

#: The complete allow-list per module: what it may import, and nothing else.
#: An empty tuple means the module imports nothing else in the application.
ALLOWED: dict[str, tuple[str, ...]] = {
    # The future orchestrator: the only module allowed to know everything.
    "AI Core": tuple(name for name in MODULES if name != "AI Core"),
    "Director AI": ("Contracts", "Prompt Compiler", "Cinematic Knowledge"),
    "Storyboard Engine": ("Contracts", "Director AI", "Cinematic Knowledge"),
    "Render Engine": ("Contracts", "Prompt Compiler", "Provider Registry", "Storage", "Persistence"),
    "Provider Registry": ("Contracts", "Runtime Config"),
    "Campaign Builder": ("Contracts", "Prompt Compiler", "Storage", "Persistence"),
    "Quality Engine": ("Contracts", "Persistence"),
    "Persona Engine": ("Contracts", "Persistence"),
    "Database Guard": ("Runtime Config",),
    "Contracts": (),
    "Prompt Compiler": ("Contracts",),
    "Cinematic Knowledge": ("Contracts", "Persistence"),
    "Spec Builder": ("Contracts", "Cinematic Knowledge", "Persona Engine", "Prompt Compiler"),
    "Job Queue": (
        "Contracts",
        "Runtime Config",
        "Persistence",
        "Persona Engine",
        "Provider Registry",
        "Quality Engine",
        "Spec Builder",
        "Storage",
        "Application Boundary",
    ),
    "Continuity Engine": ("Persistence",),
    "Knowledge Graph": ("Persistence",),
    "Storage": ("Persistence", "Runtime Config"),
    "Persistence": ("Runtime Config",),
    "Security": ("Persistence", "Runtime Config"),
    "Runtime Config": (),
    # The composition root: wiring lives here by design (ETAPA 2).
    "Application Boundary": tuple(
        name for name in MODULES if name not in {"Application Boundary", "AI Core", "Dead Cluster"}
    ),
    # Dead and broken by decision (AUDIT.md P0-1). Frozen where it is.
    "Dead Cluster": ("Application Boundary", "Runtime Config"),
    # `app/core/__init__.py` re-exports the Core family; `app/__init__.py` is a docstring.
    "Package Root": (
        "Contracts",
        "Cinematic Knowledge",
        "Director AI",
        "Job Queue",
        "Persona Engine",
        "Prompt Compiler",
        "Quality Engine",
        "Spec Builder",
        "Storyboard Engine",
    ),
}

#: The five prohibitions PR010.0 states in words, restated here so the test
#: reads like the requirement. They are implied by ALLOWED, and asserting them
#: separately means a careless widening of an allow-list still fails.
FORBIDDEN: tuple[tuple[str, str, str], ...] = (
    ("Director AI", "Provider Registry", "planning must not depend on the hardware that executes it"),
    ("Quality Engine", "Render Engine", "a verdict must recommend, never execute"),
    ("Provider Registry", "Director AI", "execution must not interpret intention"),
    ("Campaign Builder", "Quality Engine", "a campaign plan must not be rewritten by a score"),
    ("Storyboard Engine", "Provider Registry", "planning must not depend on the hardware that executes it"),
    ("Render Engine", "Director AI", "rendering executes a plan, it does not make one"),
    ("Quality Engine", "Provider Registry", "scoring an artifact must not reach the GPU layer"),
)


#: Prefixes that match **only themselves**, never their descendants.
#: `app` and `app.core` are namespace packages whose `__init__` re-exports the
#: family; if they matched by prefix they would own the entire tree and
#: `test_every_backend_file_has_an_owner` would be vacuously green — a new
#: undeclared package would inherit Package Root's allow-list instead of
#: failing. Learned the hard way while writing this guard.
EXACT_ONLY: frozenset[str] = frozenset({"app", "app.core"})


def _owner_index() -> list[tuple[str, str]]:
    """(package prefix, module name), longest prefix first."""

    pairs = [(prefix, name) for name, prefixes in MODULES.items() for prefix in prefixes]
    return sorted(pairs, key=lambda item: len(item[0]), reverse=True)


OWNERS = _owner_index()


def owner_of(module: str) -> str | None:
    for prefix, name in OWNERS:
        if module == prefix:
            return name
        if prefix not in EXACT_ONLY and module.startswith(prefix + "."):
            return name
    return None


def module_name(path: pathlib.Path, app_root: pathlib.Path) -> str:
    parts = list(path.relative_to(app_root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return "app." + ".".join(parts) if parts else "app"


def imports_of(path: pathlib.Path, module: str) -> set[str]:
    """Every `app.*` module this file imports, relative imports resolved.

    Both real imports and `if TYPE_CHECKING:` imports are collected. A type-only
    import is still a declared dependency on another module's vocabulary, and
    the freeze is about the shape of the architecture, not only about what the
    interpreter happens to execute.
    """

    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = module.split(".")
                if path.name != "__init__.py":
                    base = base[:-1]
                climb = node.level - 1
                if climb:
                    base = base[: len(base) - climb]
                found.add(".".join(base + ([node.module] if node.module else [])))
            elif node.module and node.module.split(".")[0] == "app":
                found.add(node.module)
        elif isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names if alias.name.split(".")[0] == "app"}
    return {name for name in found if name.split(".")[0] == "app"}


def build_graph(app_root: pathlib.Path) -> tuple[dict[str, set[str]], dict[tuple[str, str], list[str]]]:
    """Module-level import graph plus, for each edge, the files that create it."""

    graph: dict[str, set[str]] = defaultdict(set)
    evidence: dict[tuple[str, str], list[str]] = defaultdict(list)
    for path in sorted(app_root.rglob("*.py")):
        module = module_name(path, app_root)
        source_owner = owner_of(module)
        if source_owner is None:
            continue
        for target in sorted(imports_of(path, module)):
            target_owner = owner_of(target)
            if target_owner is None or target_owner == source_owner:
                continue
            graph[source_owner].add(target_owner)
            evidence[(source_owner, target_owner)].append(f"{module} imports {target}")
    return graph, evidence


@pytest.fixture(scope="module")
def graph() -> dict[str, set[str]]:
    return build_graph(APP)[0]


@pytest.fixture(scope="module")
def evidence() -> dict[tuple[str, str], list[str]]:
    return build_graph(APP)[1]


def _path_between(graph: dict[str, set[str]], start: str, goal: str) -> list[str] | None:
    """Shortest import path from `start` to `goal`, or None. BFS, so the
    failure message shows the shortest explanation of the coupling."""

    queue: deque[list[str]] = deque([[start]])
    seen = {start}
    while queue:
        trail = queue.popleft()
        for nxt in sorted(graph.get(trail[-1], ())):
            if nxt == goal:
                return trail + [nxt]
            if nxt not in seen:
                seen.add(nxt)
                queue.append(trail + [nxt])
    return None


# ---------------------------------------------------------------------------
# Every file has an owner — no holes in the allow-list
# ---------------------------------------------------------------------------


def test_every_backend_file_has_an_owner() -> None:
    """A new package must be declared in the manifest before it can be merged.

    Without this, an unclassified file would be an invisible corridor between
    two modules that are forbidden to know each other.
    """

    orphans = [
        module_name(path, APP)
        for path in sorted(APP.rglob("*.py"))
        if owner_of(module_name(path, APP)) is None
    ]
    assert not orphans, (
        "these modules belong to no declared module — add them to "
        f"docs/ARCHITECTURE_MANIFEST.md and to MODULES: {orphans}"
    )


def test_every_declared_module_has_an_allow_list() -> None:
    assert set(MODULES) == set(ALLOWED), sorted(set(MODULES) ^ set(ALLOWED))


def test_every_allow_list_names_real_modules() -> None:
    for name, allowed in ALLOWED.items():
        unknown = sorted(set(allowed) - set(MODULES))
        assert not unknown, f"{name} allows unknown modules: {unknown}"
        assert name not in allowed, f"{name} lists itself"


# ---------------------------------------------------------------------------
# The four prohibitions PR010.0 names, plus the AI Core asymmetry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("source", "target", "why"), FORBIDDEN)
def test_forbidden_dependency_is_absent(graph, evidence, source: str, target: str, why: str) -> None:
    """Direct coupling: the import that must never be written."""

    assert target not in graph.get(source, set()), (
        f"{source} must not import {target} — {why}. Offending imports: "
        f"{evidence.get((source, target), [])}"
    )


@pytest.mark.parametrize(("source", "target", "why"), FORBIDDEN)
def test_forbidden_dependency_is_absent_transitively(graph, source: str, target: str, why: str) -> None:
    """The same rule through intermediaries, so a pass-through cannot defeat it."""

    trail = _path_between(graph, source, target)
    assert trail is None, f"{source} reaches {target} via {' -> '.join(trail)} — {why}"


def test_director_does_not_import_providers(graph) -> None:
    """PR010.0, stated in its own words.

    The Director decides what to film. Which GPU, checkpoint or adapter runs is
    the Registry's decision — if planning depended on it, a plan would stop
    being reproducible on a different machine.
    """

    assert "Provider Registry" not in graph.get("Director AI", set())


def test_quality_does_not_import_render(graph) -> None:
    """PR010.0: a verdict recommends, it never executes.

    If the Quality Engine could import the Render Engine, "score 62 → regenerate"
    would stop being a sentence on screen and start spending GPU time by itself.
    """

    assert "Render Engine" not in graph.get("Quality Engine", set())


def test_providers_do_not_import_director(graph) -> None:
    """PR010.0: a provider receives a spec and returns an artifact. Nothing else."""

    assert "Director AI" not in graph.get("Provider Registry", set())


def test_campaign_does_not_import_quality(graph) -> None:
    """PR010.0: a commercial plan is not edited by a score."""

    assert "Quality Engine" not in graph.get("Campaign Builder", set())


def test_ai_core_is_the_only_module_allowed_to_know_everything() -> None:
    """The asymmetry, frozen before the module exists.

    AI Core may import every module; no module may import AI Core. Declaring it
    now means the boundary is already enforced on the day the package is
    created, rather than being retrofitted after the first coupling.
    """

    assert set(ALLOWED["AI Core"]) == set(MODULES) - {"AI Core"}
    importers = sorted(name for name, allowed in ALLOWED.items() if "AI Core" in allowed)
    assert importers == [], f"nothing may import AI Core, but these declare it: {importers}"


def test_nothing_imports_the_ai_core_package_today(graph) -> None:
    """Belt and braces: the rule is checked against the real graph too."""

    offenders = sorted(name for name, targets in graph.items() if "AI Core" in targets)
    assert offenders == [], f"AI Core must not be imported, but is by: {offenders}"


# ---------------------------------------------------------------------------
# The whole graph, not only the named rules
# ---------------------------------------------------------------------------


def test_no_module_imports_outside_its_allow_list(graph, evidence) -> None:
    """The freeze itself: every edge in the codebase is one the manifest allows.

    A new dependency — even a harmless-looking one — fails here until it is
    declared. That is deliberate: the cost of adding coupling should be a
    conscious edit to `docs/ARCHITECTURE_MANIFEST.md`, reviewed like any other
    architectural decision.
    """

    violations: list[str] = []
    for source, targets in sorted(graph.items()):
        for target in sorted(targets - set(ALLOWED[source])):
            violations.append(
                f"{source} -> {target} (not in its allow-list): {evidence[(source, target)][:3]}"
            )
    assert not violations, "undeclared dependencies:\n" + "\n".join(violations)


def test_the_contracts_module_depends_on_nothing(graph) -> None:
    """Contracts are the shared language, so they cannot carry dependencies.

    If `app.contracts` imported a domain module, every module would inherit
    that module transitively — and the vocabulary would stop being neutral.
    """

    assert graph.get("Contracts", set()) == set()


def test_the_import_graph_is_acyclic(graph) -> None:
    """A cycle between modules means neither can be reasoned about alone.

    The Application Boundary is excluded: `app.schemas` imports `app.events`
    for the status mapping while the queue imports the schemas, which is a
    composition-root convenience that predates this PR and is documented in the
    manifest rather than silently allowed everywhere.
    """

    nodes = [name for name in MODULES if name not in {"Application Boundary", "Dead Cluster"}]
    edges = {name: {t for t in graph.get(name, set()) if t in nodes} for name in nodes}

    visiting: set[str] = set()
    done: set[str] = set()
    cycles: list[str] = []

    def visit(node: str, trail: list[str]) -> None:
        if node in done:
            return
        if node in visiting:
            start = trail.index(node)
            cycles.append(" -> ".join(trail[start:] + [node]))
            return
        visiting.add(node)
        for nxt in sorted(edges[node]):
            visit(nxt, trail + [nxt])
        visiting.discard(node)
        done.add(node)

    for node in nodes:
        visit(node, [node])
    assert not cycles, f"import cycles: {cycles}"


# ---------------------------------------------------------------------------
# ETAPA 4 — contracts are the single shared language
# ---------------------------------------------------------------------------


def test_the_contracts_package_exists_and_is_the_canonical_home() -> None:
    package = APP / "contracts"
    assert package.is_dir(), "PR010.0 ETAPA 4 requires backend/app/contracts/"
    assert (package / "__init__.py").is_file()
    for domain in ("generation", "prompt", "persona", "cinematic", "direction", "graph"):
        assert (package / f"{domain}.py").is_file(), f"missing contracts/{domain}.py"


def test_the_legacy_contracts_path_reexports_the_same_objects() -> None:
    """Identity, not equality: there must be exactly one definition of each.

    `app.core.contracts` predates the freeze and is imported by twenty modules
    and most of the suite, so it keeps working (Bible §2: never break an
    existing import). It is a façade — if these ever stopped being the same
    object, a contract would have been forked.
    """

    import app.contracts as canonical
    import app.core.contracts as legacy

    for name in canonical.__all__:
        assert hasattr(legacy, name), f"the façade dropped {name}"
        assert getattr(legacy, name) is getattr(canonical, name), f"{name} was forked, not re-exported"


def test_the_facade_adds_nothing_of_its_own() -> None:
    """The old path must export the same surface, no more and no less."""

    import app.contracts as canonical
    import app.core.contracts as legacy

    assert set(legacy.__all__) == set(canonical.__all__)


def test_no_module_defines_a_duplicate_contract() -> None:
    """"Nenhum módulo pode definir contratos duplicados" — checked by AST.

    A second class with a contract's name anywhere outside `app/contracts/` is
    a fork waiting to drift, so it fails here. `app/schemas.py` is excluded:
    Pydantic request/response models are the HTTP wire shape, a different
    concern that the manifest assigns to the Application Boundary.
    """

    import app.contracts as canonical

    reserved = set(canonical.__all__)
    offenders: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        if path.is_relative_to(APP / "contracts") or path == APP / "core" / "contracts.py":
            continue
        if path == APP / "schemas.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in reserved:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} redefines {node.name}")
    assert not offenders, "duplicated contracts:\n" + "\n".join(offenders)


def test_the_contracts_package_imports_nothing_from_the_application() -> None:
    """Vocabulary cannot depend on behaviour, or it stops being neutral."""

    for path in sorted((APP / "contracts").rglob("*.py")):
        module = module_name(path, APP)
        external = {name for name in imports_of(path, module) if not name.startswith("app.contracts")}
        assert not external, f"{module} imports application code: {sorted(external)}"


def test_the_contracts_package_is_framework_free() -> None:
    """Same rule the Core has lived under since ETAPA 2, applied to its vocabulary."""

    banned = {"fastapi", "starlette", "sqlalchemy", "celery", "boto3", "pydantic", "pydantic_settings", "redis"}
    for path in sorted((APP / "contracts").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                imported.add(node.module.split(".")[0])
        assert not (imported & banned), f"{path.name} imports {sorted(imported & banned)}"


def test_a_contract_never_decides_anything() -> None:
    """Contracts carry shape, not policy.

    The rule the original module stated in prose ("a contract never decides
    anything"), made checkable: no contract may call out to a database, the
    filesystem or the network.

    Measured on *called names*, not on raw text, and following the repository's
    `_code_only` convention (`test_project_memory_contract.py`): the sources
    legitimately mention `StoryboardEngine.as_beats` in a comment explaining who
    fills a field, and a substring scan would fail on the documentation while
    proving nothing about the code.
    """

    banned = {"open", "execute", "commit", "connect", "get", "post", "request", "run", "query"}
    for path in sorted((APP / "contracts").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        called: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
        hits = sorted(called & banned)
        assert not hits, f"{path.name} calls {hits} — behaviour belongs to the module that owns it"


# ---------------------------------------------------------------------------
# The manifest and the guard must agree
# ---------------------------------------------------------------------------


def test_the_manifest_exists() -> None:
    assert MANIFEST.is_file(), "PR010.0 ETAPA 1 requires docs/ARCHITECTURE_MANIFEST.md"


@pytest.mark.parametrize(
    "module",
    [
        "AI Core",
        "Director AI",
        "Storyboard Engine",
        "Render Engine",
        "Provider Registry",
        "Campaign Builder",
        "Quality Engine",
        "Persona Engine",
        "Database Guard",
        "Network Layer",
    ],
)
def test_the_manifest_declares_every_required_module(module: str) -> None:
    """The ten modules PR010.0 lists, each with the four declared fields."""

    text = MANIFEST.read_text(encoding="utf-8")
    heading = re.search(rf"^## {re.escape(module)}\b.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert heading, f"{module} has no section in the manifest"
    section = heading.group(1)
    for field in ("Owner", "Responsabilidade", "Dependências permitidas", "Dependências proibidas"):
        assert field in section, f"{module} does not declare {field}"


def test_the_manifest_lists_every_module_the_guard_knows() -> None:
    """Prose and guard cannot drift: the ownership table names them all."""

    text = MANIFEST.read_text(encoding="utf-8")
    for module in MODULES:
        assert f"**{module}**" in text or f"| {module} |" in text, f"{module} is missing from the manifest"


def test_the_manifest_states_the_four_prohibitions() -> None:
    text = MANIFEST.read_text(encoding="utf-8")
    for fragment in (
        "Director NÃO importa Providers",
        "Quality NÃO importa Render",
        "Providers NÃO importam Director",
        "Campaign NÃO importa Quality",
    ):
        assert fragment in text, f"the manifest must state: {fragment}"


# ---------------------------------------------------------------------------
# The guard must be able to fail
# ---------------------------------------------------------------------------


def test_the_guard_detects_a_planted_violation(tmp_path: pathlib.Path) -> None:
    """A green guard is only meaningful if a red one is reachable.

    A copy of the tree gets the exact import PR010.0 forbids — the Director
    reaching for the Provider Registry — and the graph builder must see it.
    """

    clone = tmp_path / "app"
    shutil.copytree(APP, clone)
    target = clone / "core" / "director" / "director_agent.py"
    target.write_text(
        "from ...providers.provider_registry import ProviderRegistry\n"
        + target.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    graph, _ = build_graph(clone)

    assert "Provider Registry" in graph["Director AI"], "the guard cannot see a direct violation"
    trail = _path_between(graph, "Director AI", "Provider Registry")
    assert trail == ["Director AI", "Provider Registry"]


def test_the_guard_detects_a_transitive_violation(tmp_path: pathlib.Path) -> None:
    """The same, laundered through a third module.

    Quality reaches Render by way of the Campaign Builder. A guard that only
    looked at direct edges would call this clean.
    """

    clone = tmp_path / "app"
    shutil.copytree(APP, clone)
    quality = clone / "quality" / "quality_engine.py"
    quality.write_text(
        "from ..campaign.campaign_service import CampaignService\n" + quality.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    campaign = clone / "campaign" / "campaign_service.py"
    campaign.write_text(
        "from ..render.render_orchestrator import RenderOrchestrator\n" + campaign.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    graph, _ = build_graph(clone)

    assert "Render Engine" not in graph["Quality Engine"], "sanity: the planted edge is indirect"
    trail = _path_between(graph, "Quality Engine", "Render Engine")
    assert trail == ["Quality Engine", "Campaign Builder", "Render Engine"]


def test_the_guard_detects_an_unowned_module(tmp_path: pathlib.Path) -> None:
    """A brand-new package must be declared before it can be used."""

    clone = tmp_path / "app"
    shutil.copytree(APP, clone)
    (clone / "smuggler").mkdir()
    (clone / "smuggler" / "__init__.py").write_text("", encoding="utf-8")

    orphans = [
        module_name(path, clone)
        for path in sorted(clone.rglob("*.py"))
        if owner_of(module_name(path, clone)) is None
    ]
    assert orphans == ["app.smuggler"]


def test_the_suite_fails_when_a_boundary_is_crossed(tmp_path: pathlib.Path) -> None:
    """End to end: a planted violation must turn this test file red.

    The strongest available proof that the guard is wired to CI rather than
    merely computing something. `pytest` runs against a patched copy of the
    repository, and its exit status must be non-zero.
    """

    workspace = tmp_path / "repo"
    workspace.mkdir()
    shutil.copytree(APP, workspace / "app")
    shutil.copy(pathlib.Path(__file__), workspace / "test_boundaries.py")
    (workspace / "docs").mkdir()
    shutil.copy(MANIFEST, workspace / "docs" / "ARCHITECTURE_MANIFEST.md")

    target = workspace / "app" / "providers" / "provider_registry.py"
    target.write_text(
        "from ..core.director_agent import DirectorAgent\n" + target.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    # The copied guard resolves ROOT as <workspace>/.. — point it at the clone.
    # `count=1` matters: the strings being replaced also appear inside *this*
    # test as literals, and replacing those produced a file that could not be
    # parsed (the clone failed to collect, which looked like a caught violation
    # but proved nothing).
    patched = (workspace / "test_boundaries.py").read_text(encoding="utf-8")
    patched = patched.replace(
        "ROOT = pathlib.Path(__file__).resolve().parents[2]",
        f"ROOT = pathlib.Path({str(workspace)!r})",
        1,
    ).replace(
        'APP = ROOT / "backend" / "app"',
        'APP = ROOT / "app"',
        1,
    )
    (workspace / "test_boundaries.py").write_text(patched, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(workspace / "test_boundaries.py"),
            # No `-x`: the parametrized rule fails first and would stop the run
            # before the named guard below ever executed.
            "-q",
            "-p",
            "no:cacheprovider",
            "-k",
            "providers_do_not_import_director or forbidden_dependency_is_absent",
        ],
        capture_output=True,
        text=True,
        cwd=workspace,
        timeout=300,
    )

    assert result.returncode != 0, "a forbidden import did not fail the suite:\n" + result.stdout[-2000:]
    # A collection error would also be non-zero, so require a real assertion
    # failure naming the boundary that was crossed.
    assert "error" not in result.stdout.lower().split("short test summary")[0][:200], (
        "the clone failed to collect instead of failing the guard:\n" + result.stdout[-2000:]
    )
    assert "test_providers_do_not_import_director" in result.stdout
    assert "Director AI" in result.stdout


def test_the_guard_is_not_trivially_green() -> None:
    """The rules must be about edges that could plausibly exist.

    Every forbidden pair names two modules that really are in the manifest, so
    none of the prohibitions is a tautology about something absent.
    """

    for source, target, _ in FORBIDDEN:
        assert source in MODULES, source
        assert target in MODULES, target
