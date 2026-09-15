"""Independence: each Core component must import and run alone.

The mission requires "Todos devem ser independentes". This test enforces it
structurally rather than by inspection: each module is imported in a *fresh
interpreter* with `app.core.__init__` stubbed out, then the test asserts none
of its siblings were pulled in.

Stubbing the package `__init__` matters. Without it, importing any submodule
first executes `app/core/__init__.py`, which imports the whole family and makes
every module look coupled.

GenerationSpecBuilder is the declared composition root, so it is the one
component allowed to import the others.
"""
import subprocess
import sys
from pathlib import Path

import pytest

#: Modules that must not import each other.
INDEPENDENT_MODULES = (
    "app.core.contracts",
    "app.core.memory_resolver",
    "app.core.style_resolver",
    "app.core.shot_resolver",
    "app.core.prompt_compiler",
    "app.core.director_agent",
    "app.core.timeline",
    "app.core.quality",
)

#: Probe run in a clean interpreter. It installs an empty `app.core` package so
#: the real `__init__.py` never runs, imports exactly one target module, then
#: reports what the import graph actually pulled in.
#:
#: The backend root is injected explicitly: the subprocess must not depend on
#: PYTHONPATH being set by the caller, otherwise this test only passes under
#: the exact CI invocation and fails under coverage or a bare `pytest`.
_PROBE = """
import importlib, pathlib, sys, types
sys.path.insert(0, {backend_root!r})
import app
package = types.ModuleType("app.core")
package.__path__ = [str(pathlib.Path(app.__file__).resolve().parent / "core")]
sys.modules["app.core"] = package
importlib.import_module({target!r})
wanted = {{m for m in sys.modules if m.startswith("app.core.")}}
banned = {{m.split(".")[0] for m in sys.modules}} & {banned!r}
print("CORE=" + ",".join(sorted(wanted)))
print("FRAMEWORK=" + ",".join(sorted(banned)))
"""

BANNED_FRAMEWORKS = {"fastapi", "starlette", "sqlalchemy", "celery", "boto3", "pydantic_settings"}


def _backend_root() -> str:
    import app

    return str(Path(app.__file__).resolve().parents[1])


def _probe(module: str) -> dict[str, set[str]]:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _PROBE.format(target=module, banned=BANNED_FRAMEWORKS, backend_root=_backend_root()),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"probe failed for {module}:\n{result.stderr}"
    parsed: dict[str, set[str]] = {}
    for line in result.stdout.strip().splitlines():
        key, _, value = line.partition("=")
        parsed[key] = {item for item in value.split(",") if item}
    return parsed


@pytest.mark.parametrize("module", INDEPENDENT_MODULES)
def test_module_imports_without_any_sibling(module: str) -> None:
    loaded = _probe(module)["CORE"]
    unexpected = sorted(m for m in loaded if m not in {module, "app.core.contracts"})
    assert not unexpected, f"{module} pulled in {unexpected}"


@pytest.mark.parametrize("module", INDEPENDENT_MODULES)
def test_module_does_not_depend_on_the_application_layer(module: str) -> None:
    """The Core must not import FastAPI, SQLAlchemy, Celery, boto3 or settings."""

    assert _probe(module)["FRAMEWORK"] == set()


def test_every_component_shares_only_the_contracts_vocabulary() -> None:
    for module in INDEPENDENT_MODULES:
        if module == "app.core.contracts":
            continue
        assert "app.core.contracts" in _probe(module)["CORE"], f"{module} must share the contracts"


def test_the_composition_root_may_import_the_components() -> None:
    loaded = _probe("app.core.generation_spec_builder")["CORE"]
    for expected in (
        "app.core.memory_resolver",
        "app.core.style_resolver",
        "app.core.shot_resolver",
        "app.core.prompt_compiler",
    ):
        assert expected in loaded, f"composition root is missing {expected}"


def test_no_component_imports_a_peer_directly() -> None:
    """Static guard, in case the runtime probe is ever weakened."""

    import app

    core_dir = Path(app.__file__).resolve().parent / "core"
    peers = (
        "memory_resolver",
        "style_resolver",
        "shot_resolver",
        "prompt_compiler",
        "director_agent",
    )
    for owner in peers:
        source = (core_dir / f"{owner}.py").read_text(encoding="utf-8")
        for peer in peers:
            if peer == owner:
                continue
            assert f"from .{peer}" not in source, f"{owner} imports its peer {peer}"


def test_every_component_is_instantiable_with_no_arguments() -> None:
    from app.core import (
        DirectorAgent,
        GenerationSpecBuilder,
        MemoryResolver,
        PromptCompiler,
        ShotResolver,
        StyleResolver,
    )

    for component in (
        MemoryResolver(),
        StyleResolver(),
        ShotResolver(),
        PromptCompiler(),
        DirectorAgent(),
        GenerationSpecBuilder(),
    ):
        assert component is not None


def test_all_six_core_components_are_exported() -> None:
    import app.core as core

    for name in (
        "DirectorAgent",
        "MemoryResolver",
        "PromptCompiler",
        "StyleResolver",
        "ShotResolver",
        "GenerationSpecBuilder",
    ):
        assert hasattr(core, name), f"missing Core component: {name}"
        assert name in core.__all__


def test_every_exported_name_actually_exists() -> None:
    """`__all__` must not advertise what the module does not have.

    ETAPA 13 removed a constant and left its `__all__` entry behind, so
    `from app.core import *` raised AttributeError. Nothing caught it because no
    test does a star-import, and the package is imported by name everywhere.
    """

    import importlib

    package = importlib.import_module("app.core")
    missing = [name for name in package.__all__ if not hasattr(package, name)]
    assert not missing, f"__all__ advertises names that do not exist: {missing}"


def test_the_star_import_works() -> None:
    """The same guarantee, exercised the way a consumer would."""

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, {root!r}); "
            "exec('from app.core import *')".format(root=_backend_root()),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
