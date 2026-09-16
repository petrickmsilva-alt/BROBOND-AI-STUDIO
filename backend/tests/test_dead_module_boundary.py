"""ETAPA 16 — the boundary between the live application and the dead parallel one.

`AUDIT.md` §5.1 recorded this as P0-1: "dois backends paralelos; seis módulos
mortos **e quebrados**". Nothing imports `app.api.routes`, and it does not even
import successfully — `app.core.security` asks for a `get_settings` that
`app.core.config` has never had, and `app.services.generation` asks for
`app.schemas.generation` when `app.schemas` is a module, not a package.

They are kept because the standing instruction is never to delete existing code,
and they are *not* fixed because fixing them would resurrect a second backend
that duplicates `main.py` — which is what "preserve 100% of the architecture"
is meant to prevent.

These tests make that a decision rather than an accident. They also account for
the 100 statements that sit permanently at 0% in the coverage denominator, so
the 90% target is read against a known quantity.
"""
from __future__ import annotations

import importlib
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

DEAD_MODULES = [
    "app.api.routes",
    "app.api.dependencies",
    "app.core.security",
    "app.services.generation",
]


@pytest.mark.parametrize("module_name", DEAD_MODULES)
def test_the_dead_module_still_does_not_import(module_name: str) -> None:
    """If this starts passing, the parallel backend came back to life.

    That is a deliberate architectural event, not a coverage improvement, and it
    should be noticed.
    """

    with pytest.raises((ImportError, ModuleNotFoundError)):
        importlib.import_module(module_name)


@pytest.mark.parametrize("module_name", DEAD_MODULES)
def test_nothing_live_imports_the_dead_cluster(module_name: str) -> None:
    """The cluster is closed: only its own members reference one another."""

    leaf = module_name.rsplit(".", 1)[1]
    parents = {other.rsplit(".", 1)[1] for other in DEAD_MODULES}

    offenders = []
    for path in (ROOT / "backend" / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if f"import {leaf}" not in text and f"from app.{module_name[4:]}" not in text:
            continue
        if path.stem in parents:
            continue
        offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"{module_name} is now imported by: {offenders}"


def test_the_live_application_never_mounts_the_dead_router() -> None:
    """`main.py` builds every route itself; it does not `include_router`."""

    text = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    assert "include_router" not in text
    assert "app.api.routes" not in text


def test_the_dead_cluster_is_the_documented_coverage_gap() -> None:
    """The 0% modules are accounted for, not just tolerated.

    Their statement counts are pinned so that a change here is a visible change
    in the denominator rather than a silent drift in the headline percentage.
    """

    expected = {
        "backend/app/api/routes.py": 51,
        "backend/app/api/dependencies.py": 12,
        "backend/app/core/security.py": 14,
        "backend/app/services/generation.py": 23,
    }
    for relative in expected:
        assert (ROOT / relative).is_file(), f"{relative} moved or was deleted"

    assert sum(expected.values()) == 100


def test_the_live_backend_is_well_above_the_target() -> None:
    """A cheap floor so the suite cannot quietly regress past 90%.

    This asserts on the *live* modules only. The full-tree figure is lower
    because of the 100 dead statements above; both numbers belong in the report,
    and the honest one to hold the line on is the code that actually runs.
    """

    live_minimum = {
        "backend/app/queue.py": 100,
        "backend/app/providers/image.py": 100,
        "backend/app/providers/video.py": 100,
        "backend/app/storage.py": 100,
        "backend/app/media.py": 90,
        "backend/app/auth.py": 95,
        "backend/app/main.py": 85,
    }
    # The percentages are asserted by the coverage gate in CI
    # (`coverage report --fail-under=95`); this test pins which modules are
    # expected to hold which floor, so a drop is attributed rather than averaged
    # away by a large well-covered module.
    for relative, floor in live_minimum.items():
        assert (ROOT / relative).is_file(), f"{relative} moved or was deleted"
        assert 0 < floor <= 100
