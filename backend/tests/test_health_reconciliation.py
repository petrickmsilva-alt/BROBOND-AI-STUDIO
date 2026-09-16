"""PR009.1 — Health Check Reconciliation: FastAPI ↔ render.yaml, pinned by test.

Render's probes are unauthenticated GETs against ``healthCheckPath``; if that
path stops being a public 200-OK route of the deployed app, the platform
restarts a healthy service (or the UI reads "offline"). The original audit
found the two already agreed — this suite keeps them from drifting apart:

* both health routes answer 200 with the documented body (``/health`` and
  ``/api/v1/health`` are stacked decorators on one handler);
* neither declares an identity dependency — a probe without a token passes;
* every ``healthCheckPath`` in ``render.yaml`` resolves to a route the app
  actually serves (the web service's ``/`` belongs to Next.js and is noted
  as such);
* the versioned health route keeps the global ``/api/v1`` prefix — the
  hotfix rule is that the prefix never moves.
"""
from __future__ import annotations

import inspect
import pathlib
import re

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ROOT = pathlib.Path(__file__).resolve().parents[2]
RENDER_YAML = ROOT / "render.yaml"

HEALTH_BODY_KEYS = {"status", "service", "mode"}


def _render_service_health_paths() -> dict[str, str]:
    """``{service name: healthCheckPath}`` from render.yaml, no YAML dependency.

    The blueprint is flat and regular (``services:`` → ``- type:`` blocks with
    ``name:`` and ``healthCheckPath:``), so a two-state line scan is enough and
    keeps the test suite free of a PyYAML pin.
    """

    services: dict[str, str] = {}
    current: str | None = None
    for raw in RENDER_YAML.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("- type:"):
            current = None  # a new service block starts; `name:` may follow
            continue
        name_match = re.match(r"name:\s*(\S+)", line)
        if name_match and current is None:
            current = name_match.group(1)
            continue
        path_match = re.match(r"healthCheckPath:\s*(\S+)", line)
        if path_match and current is not None:
            services[current] = path_match.group(1)
            current = None
    return services


def _served_get_paths() -> set[str]:
    return {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and "GET" in route.methods
    }


def _has_identity_dependency(path: str) -> bool:
    """True when the route declares a `user` parameter (token required)."""

    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and "GET" in route.methods:
            if "user" in inspect.signature(route.endpoint).parameters:
                return True
    return False


# ---------------------------------------------------------------------------
# The health routes themselves
# ---------------------------------------------------------------------------


def test_versioned_health_answers_200_with_the_documented_body() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "brobond-api"
    assert HEALTH_BODY_KEYS <= set(body)


def test_root_health_alias_answers_the_same_way() -> None:
    versioned = client.get("/api/v1/health")
    alias = client.get("/health")

    assert alias.status_code == 200
    assert alias.json()["status"] == "ok"
    assert alias.json() == versioned.json()


def test_health_never_asks_a_probe_for_a_token() -> None:
    """Render's health checks are unauthenticated: a 401 would restart the service."""

    anonymous_versioned = client.get("/api/v1/health")
    anonymous_alias = client.get("/health")

    assert anonymous_versioned.status_code == 200
    assert anonymous_alias.status_code == 200
    assert not _has_identity_dependency("/api/v1/health")
    assert not _has_identity_dependency("/health")


def test_the_versioned_health_keeps_the_global_api_prefix() -> None:
    """The hotfix rule: the `/api/v1` prefix never moves."""

    assert "/api/v1/health" in _served_get_paths()


# ---------------------------------------------------------------------------
# Reconciliation with render.yaml
# ---------------------------------------------------------------------------


def test_render_yaml_declares_a_health_check_for_every_web_service() -> None:
    services = _render_service_health_paths()

    assert "brobond-ai-api" in services, "the API service lost its healthCheckPath"
    assert "brobond-studio-web" in services, "the web service lost its healthCheckPath"


def test_the_render_api_health_path_is_a_real_public_200_route() -> None:
    path = _render_service_health_paths()["brobond-ai-api"]

    assert path in _served_get_paths(), f"render.yaml probes {path!r}; the API does not serve it"
    assert client.get(path).status_code == 200
    assert not _has_identity_dependency(path), "a probe without a token must pass"


def test_the_render_web_health_path_is_the_nextjs_root() -> None:
    """`/` is served by Next.js (200, verified against the dev/production server);
    the backend test suite can only pin that the blueprint keeps pointing there."""

    assert _render_service_health_paths()["brobond-studio-web"] == "/"


def test_the_render_blueprint_matches_the_documented_health_paths() -> None:
    """The values the report states are the values the blueprint carries."""

    services = _render_service_health_paths()
    assert services == {
        "brobond-studio-web": "/",
        "brobond-ai-api": "/api/v1/health",
    }
