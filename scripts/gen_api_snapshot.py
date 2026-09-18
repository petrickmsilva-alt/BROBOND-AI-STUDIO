"""Generate `docs/API_SNAPSHOT.json` from the live FastAPI application.

PR010.0 — Platform Freeze, ETAPA 3. This is the **public surface** of the
platform, frozen: every HTTP route, every WebSocket and every public model,
derived from the running app rather than written by hand.

    PYTHONPATH=backend python scripts/gen_api_snapshot.py > docs/API_SNAPSHOT.json

`backend/tests/test_api_snapshot.py` regenerates it in memory and fails if the
committed file differs. That is the whole point: a change to the public surface
is no longer something that can happen quietly as a side effect of an unrelated
edit. It requires regenerating this file, which puts the diff in the pull
request where a human can see it.

Sibling of `scripts/gen_api_doc.py`, which renders the human-readable
`docs/API.md`. Same source of truth, two audiences: that one is prose for a
reader, this one is a machine-diffable contract.

Design notes
------------
* **Deterministic.** Every collection is sorted and the JSON is emitted with a
  fixed indent, so a diff shows a real change and never a reordering.
* **Shape, not values.** Field types are recorded; examples, descriptions and
  titles are not. The contract is "this route answers a `JobResponse` with an
  `output_url` that may be null", not how the docstring is worded.
* **Auth is part of the contract.** A route that stops requiring a token is a
  breaking security change, so `auth` is recorded per route.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from typing import Any

# Allow running from the repository root without PYTHONPATH being set.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.routing import APIRoute, APIWebSocketRoute  # noqa: E402

from app.main import app  # noqa: E402

#: Bumped by hand when the *shape of this file* changes, so a snapshot written
#: by an older generator is recognisable instead of looking like a huge diff.
SNAPSHOT_VERSION = "1.0"


def type_of(schema: dict[str, Any]) -> str:
    """Collapse a JSON-Schema fragment into one readable type string.

    `{"type": "string", "format": "uuid", "title": "Id"}` becomes `"string"`,
    and a nullable field becomes `"string|null"`. Titles and formats are
    dropped on purpose: they change when a field is renamed in Python, which
    is not a change to the wire contract.
    """

    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "anyOf" in schema:
        return "|".join(type_of(option) for option in schema["anyOf"])
    if "allOf" in schema and len(schema["allOf"]) == 1:
        return type_of(schema["allOf"][0])
    kind = schema.get("type")
    if kind == "array":
        return f"array<{type_of(schema.get('items', {}))}>"
    if kind == "object" and "additionalProperties" in schema:
        extra = schema["additionalProperties"]
        if isinstance(extra, dict) and extra:
            return f"object<{type_of(extra)}>"
    return kind or "any"


def identity_of(route: APIRoute) -> str:
    """Whether the route requires a token, merely accepts one, or is public.

    Read from the declared dependency, not from the presence of a `user`
    parameter: `Depends(optional_user)` accepts an anonymous caller and must
    not be counted as protected.
    """

    parameters = inspect.signature(route.endpoint).parameters
    if "user" not in parameters:
        return "public"
    dependency = getattr(parameters["user"].default, "dependency", None)
    name = getattr(dependency, "__name__", None)
    if name == "current_user":
        return "required"
    if name == "optional_user":
        return "optional"
    return "public"


def model_names(schema: dict[str, Any] | None) -> str | None:
    """The model a request/response body refers to, if it names one."""

    if not schema:
        return None
    content = schema.get("content", {})
    body = content.get("application/json", {}).get("schema", {})
    return type_of(body) if body else None


def collect_http(spec: dict[str, Any]) -> list[dict[str, Any]]:
    routes = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/v1"):
            continue
        methods = sorted(route.methods - {"HEAD", "OPTIONS"})
        entry: dict[str, Any] = {
            "path": route.path,
            "methods": methods,
            "tag": sorted(route.tags)[0] if route.tags else None,
            "auth": identity_of(route),
            "status_code": route.status_code or 200,
        }
        operations = spec["paths"].get(route.path, {})
        for method in methods:
            operation = operations.get(method.lower(), {})
            request = model_names(operation.get("requestBody"))
            if request:
                entry["request_model"] = request
            responses = operation.get("responses", {})
            success = responses.get(str(entry["status_code"]), {})
            response = model_names(success)
            if response:
                entry["response_model"] = response
        routes.append(entry)
    return sorted(routes, key=lambda item: (item["path"], item["methods"]))


def collect_websockets() -> list[dict[str, Any]]:
    sockets = []
    for route in app.routes:
        if not isinstance(route, APIWebSocketRoute):
            continue
        try:
            source = inspect.getsource(route.endpoint)
        except OSError:  # pragma: no cover - source is always available here
            source = ""
        sockets.append(
            {
                "path": route.path,
                # All three sockets authenticate through `?token=` because a
                # browser cannot set headers on a WebSocket handshake.
                "auth": "token" if "ws_identity" in source else "public",
            }
        )
    return sorted(sockets, key=lambda item: item["path"])


def collect_models(spec: dict[str, Any]) -> dict[str, Any]:
    models = {}
    for name, schema in spec.get("components", {}).get("schemas", {}).items():
        properties = schema.get("properties", {})
        if not properties and "enum" in schema:
            models[name] = {"enum": sorted(str(value) for value in schema["enum"])}
            continue
        models[name] = {
            "fields": {field: type_of(value) for field, value in sorted(properties.items())},
            "required": sorted(schema.get("required", [])),
        }
    return dict(sorted(models.items()))


def build() -> dict[str, Any]:
    spec = app.openapi()
    http = collect_http(spec)
    sockets = collect_websockets()
    models = collect_models(spec)
    return {
        "_comment": (
            "PR010.0 Platform Freeze — generated public API surface. Do not edit by hand: "
            "run `PYTHONPATH=backend python scripts/gen_api_snapshot.py > docs/API_SNAPSHOT.json`. "
            "backend/tests/test_api_snapshot.py fails when this file and the application disagree."
        ),
        "snapshot_version": SNAPSHOT_VERSION,
        "generator": "scripts/gen_api_snapshot.py",
        "summary": {
            "http_routes": len(http),
            "core_routes": len([r for r in http if r["path"].startswith("/api/v1/core")]),
            "websockets": len(sockets),
            "models": len(models),
            "tags": len({r["tag"] for r in http if r["tag"]}),
            "auth_required": len([r for r in http if r["auth"] == "required"]),
            "auth_optional": len([r for r in http if r["auth"] == "optional"]),
            "auth_public": len([r for r in http if r["auth"] == "public"]),
        },
        "http": http,
        "websockets": sockets,
        "models": models,
    }


def render() -> str:
    return json.dumps(build(), indent=2, ensure_ascii=False, sort_keys=False) + "\n"


if __name__ == "__main__":
    sys.stdout.write(render())
