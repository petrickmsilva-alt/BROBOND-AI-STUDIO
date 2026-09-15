"""PR004.1 — Project Memory Contract: structural guards.

The contract itself (persistence, serialization, deserialization, partial
update, clear, version compatibility) is covered behaviorally by the
frontend suite (`lib/memory/*.test.ts`, vitest, 95% coverage gate). These
guards pin the architecture rules the behavioral tests cannot see:

* components never touch `localStorage` (DoD);
* `window.localStorage` exists in exactly ONE file: the Memory Adapter;
* there is exactly ONE official key (`PROJECT_MEMORY_KEY`) and no component
  names it;
* the official contract `ProjectMemoryState` carries exactly the spec's
  fields (projectId required; all the rest optional);
* the hook exists, returns { memory, save, clear } and consumes ONLY the
  adapter;
* the legacy v0 module survives (Bible: never deleted) but delegates to the
  adapter instead of touching storage itself;
* the docs and the CHANGELOG exist and the CI runs the frontend tests.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "lib" / "memory" / "project_memory.ts"
HOOK = ROOT / "lib" / "memory" / "use_project_memory.ts"
LEGACY = ROOT / "lib" / "projectMemory.ts"
PAGE = ROOT / "app" / "page.tsx"
PERSONAS_PAGE = ROOT / "app" / "studio" / "personas" / "page.tsx"
API_CLIENT = ROOT / "lib" / "api.ts"
DOCS = ROOT / "docs" / "PROJECT_MEMORY.md"
ARCHITECTURE = ROOT / "ARCHITECTURE.md"
CHANGELOG = ROOT / "CHANGELOG.md"
WORKFLOW = ROOT / ".github" / "workflows"

CONTRACT_FIELDS = [
    "projectId",
    "workspaceId",
    "personaId",
    "wardrobeId",
    "styleId",
    "loraId",
    "cameraPreset",
    "aspectRatio",
    "lastPrompt",
    "lastPlatform",
    "duration",
    "updatedAt",
]


def _read(path: pathlib.Path) -> str:
    assert path.is_file(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def _code_only(source: str) -> str:
    """Strip comments so the guards test code, not prose.

    The sources legitimately *document* the storage rule ("never touch
    window.localStorage here") — the invariant is about what the code does.
    """

    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(line.split("//", 1)[0] for line in without_blocks.splitlines())


def _frontend_files() -> list[pathlib.Path]:
    """Every frontend PRODUCTION source file (components, pages, lib) — the
    scope the DoD constrains. Test files are excluded: they legitimately
    drive the storage seam to verify the contract."""

    files: list[pathlib.Path] = []
    for directory in ("app", "lib", "components"):
        base = ROOT / directory
        if base.is_dir():
            files.extend(
                p
                for p in base.rglob("*.ts")
                if "node_modules" not in p.parts and not p.name.endswith((".test.ts", ".test.tsx"))
            )
            files.extend(
                p
                for p in base.rglob("*.tsx")
                if "node_modules" not in p.parts and not p.name.endswith((".test.ts", ".test.tsx"))
            )
    return files


@pytest.fixture(scope="module")
def adapter_source() -> str:
    return _read(ADAPTER)


@pytest.fixture(scope="module")
def hook_source() -> str:
    return _read(HOOK)


# ---------------------------------------------------------------------------
# DoD: no component uses localStorage directly
# ---------------------------------------------------------------------------


def test_no_component_touches_local_storage() -> None:
    offenders = [
        str(p.relative_to(ROOT))
        for p in _frontend_files()
        if p != ADAPTER and "localStorage" in _code_only(p.read_text(encoding="utf-8"))
    ]
    # The adapter is the single storage boundary; everything else — including
    # every component and page — must not even name localStorage.
    assert offenders == [], f"localStorage outside the adapter: {offenders}"


def test_only_one_file_references_window_local_storage() -> None:
    hits = [
        p
        for p in _frontend_files()
        if "window.localStorage" in _code_only(p.read_text(encoding="utf-8"))
    ]
    assert [str(p.relative_to(ROOT)) for p in hits] == ["lib/memory/project_memory.ts"]


# ---------------------------------------------------------------------------
# One adapter, one official key
# ---------------------------------------------------------------------------


def test_the_adapter_exposes_exactly_the_contracted_api(adapter_source: str) -> None:
    for name in ("loadProjectMemory", "saveProjectMemory", "clearProjectMemory"):
        assert re.search(rf"export function {name}\(", adapter_source), f"missing export: {name}"
    assert "export const PROJECT_MEMORY_KEY" in adapter_source
    assert "export const PROJECT_MEMORY_VERSION" in adapter_source


def test_there_is_exactly_one_official_key(adapter_source: str) -> None:
    # A storage key is a string literal used at a storage call site. The
    # official one is PROJECT_MEMORY_KEY; the auth/legacy keys are separate,
    # named, documented seams — nothing may invent a fourth.
    allowed = {"PROJECT_MEMORY_KEY", "AUTH_TOKEN_KEY", "LEGACY_PERSONA_ID_KEY"}
    keys_defined = set(re.findall(r"export const ([A-Z][A-Z0-9_]*KEY) = ", adapter_source))
    assert keys_defined == allowed, f"unexpected keys: {keys_defined}"

    # And the components never name ANY of them raw.
    for component in (PAGE, PERSONAS_PAGE):
        text = component.read_text(encoding="utf-8")
        assert "'brobond_project_memory'" not in text
        assert "'brobond_access_token'" not in text
        assert "'brobond_persona_id'" not in text


# ---------------------------------------------------------------------------
# The official contract: ProjectMemoryState
# ---------------------------------------------------------------------------


def test_the_contract_interface_has_exactly_the_spec_fields(adapter_source: str) -> None:
    match = re.search(
        r"export interface ProjectMemoryState\s*{(.*?)}", adapter_source, re.DOTALL
    )
    assert match, "ProjectMemoryState interface is missing"
    body = match.group(1)
    for field in CONTRACT_FIELDS:
        assert re.search(rf"^\s*{field}\??\s*:", body, re.MULTILINE), f"missing field: {field}"
    # Nothing beyond the spec (plus no stray fields).
    declared = set(re.findall(r"^\s*([a-zA-Z][a-zA-Z0-9_]*)\??\s*:\s*", body, re.MULTILINE))
    assert declared == set(CONTRACT_FIELDS), f"contract drift: {declared ^ set(CONTRACT_FIELDS)}"
    # Only projectId is required (no `?`), the rest are optional.
    assert re.search(r"^\s*projectId\s*:", body, re.MULTILINE)
    for field in CONTRACT_FIELDS[1:]:
        assert re.search(rf"^\s*{field}\?\s*:", body, re.MULTILINE), f"{field} must be optional"


def test_the_legacy_v0_module_delegates_instead_of_storing() -> None:
    text = _read(LEGACY)
    # Legacy is marked, never deleted (Bible §2)…
    assert "LEGACY" in text
    # …and its CODE no longer touches storage: it delegates to the adapter.
    assert "localStorage" not in _code_only(text)
    assert "from './memory/project_memory'" in text


def test_page_consumes_the_hook_not_the_storage_layer() -> None:
    text = _read(PAGE)
    assert "useProjectMemory(PROJECT_ID)" in text
    # No direct v0 import for project memory (the legacy shim stays for old
    # imports, but Home uses the hook).
    assert "from '../lib/projectMemory'" not in text


# ---------------------------------------------------------------------------
# The hook: consumes only the adapter
# ---------------------------------------------------------------------------


def test_the_hook_consumes_only_the_adapter(hook_source: str) -> None:
    assert "export function useProjectMemory(projectId: string)" in hook_source
    assert "loadProjectMemory" in hook_source
    assert "saveProjectMemory" in hook_source
    assert "clearProjectMemory" in hook_source
    # Returns the contracted triple.
    assert re.search(r"return\s*{\s*memory,\s*save,\s*clear\s*}", hook_source)
    # No storage knowledge of its own (code, not prose).
    code = _code_only(hook_source)
    assert "localStorage" not in code
    assert "PROJECT_MEMORY_KEY" not in code
    assert "'brobond" not in code
    # React is the hook's only framework dependency (adapter stays pure).
    imports = re.findall(r"import\s+\{[^}]*\}\s+from\s+'([^']+)'", code, re.DOTALL)
    assert set(imports) == {"react", "./project_memory"}


# ---------------------------------------------------------------------------
# Tooling: runner, CI, docs
# ---------------------------------------------------------------------------


def test_the_frontend_contract_suite_is_wired_into_ci() -> None:
    workflow = next(WORKFLOW.glob("*.yml"))
    text = workflow.read_text(encoding="utf-8")
    assert "test:frontend" in text, "CI must run the Project Memory contract suite"
    manifest = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert manifest["scripts"].get("test:frontend", "").startswith("vitest")
    assert manifest["scripts"].get("test:frontend:coverage", "").startswith("vitest")
    assert "vitest" in manifest.get("devDependencies", {})


def test_project_memory_documentation_exists() -> None:
    text = _read(DOCS)
    for section in ("Contrato", "Adapter", "Hook", "PostgreSQL"):
        assert section in text, f"docs/PROJECT_MEMORY.md missing section: {section}"


def test_architecture_and_changelog_record_the_contract() -> None:
    assert "Project Memory" in _read(ARCHITECTURE)
    assert "PR004.1" in _read(CHANGELOG)
