"""Generate `docs/API.md` from the live FastAPI application.

The inventory is derived, not written by hand, so it cannot silently drift from
the routes the app actually serves. `backend/tests/test_docs_accuracy.py`
regenerates it in memory and fails if the committed file is out of date.

    PYTHONPATH=backend python scripts/gen_api_doc.py > docs/API.md
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

# Allow running from the repository root without PYTHONPATH being set.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.routing import APIRoute, APIWebSocketRoute  # noqa: E402

from app.main import app  # noqa: E402


def summary(route) -> str:
    """First line of the endpoint's docstring, falling back to its name."""

    doc = inspect.getdoc(route.endpoint) or ""
    return next((line.strip() for line in doc.split("\n") if line.strip()), "") or route.name


def collect() -> tuple[list[tuple[str, str, str, str]], list[tuple[str, str]]]:
    rows: list[tuple[str, str, str, str]] = []
    sockets: list[tuple[str, str]] = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1"):
            methods = ",".join(sorted(route.methods - {"HEAD"}))
            tag = sorted(route.tags)[0] if route.tags else "-"
            rows.append((route.path, methods, tag, summary(route)))
        elif isinstance(route, APIWebSocketRoute):
            sockets.append((route.path, summary(route)))
    return rows, sockets


def render() -> str:
    rows, sockets = collect()
    by_tag: dict[str, list] = {}
    for path, methods, tag, desc in rows:
        by_tag.setdefault(tag, []).append((path, methods, desc))

    core_count = len([row for row in rows if row[0].startswith("/api/v1/core")])
    out: list[str] = []
    add = out.append

    add("# BROBOND AI STUDIO — API\n")
    add("Inventário gerado a partir da aplicação em execução, não escrito à mão.\n")
    add("```bash")
    add("PYTHONPATH=backend python scripts/gen_api_doc.py > docs/API.md")
    add("```\n")
    add("`backend/tests/test_docs_accuracy.py` compara este arquivo com a aplicação; se uma rota")
    add("mudar e o documento não for regenerado, a suíte falha.\n")
    add("---\n")
    add("## Resumo\n")
    add(f"- **{len(rows)}** rotas HTTP sob `/api/v1`")
    add(f"- **{core_count}** delas são `/api/v1/core/*` — a camada de decisão")
    add(f"- **{len(sockets)}** WebSockets")
    add(f"- **{len(by_tag)}** tags\n")
    add("OpenAPI interativo em `/docs` (Swagger) e `/redoc` quando o serviço está no ar.\n")
    add(
        "PR006 Storyboard Cinematic Engine não adiciona rotas de render: a UI edita um "
        "`StoryboardState` versionado sobre o `ProductionPlan` retornado por "
        "`/api/v1/core/director/production-plan`. PR007 adiciona `/api/v1/providers` "
        "para health/capabilities do registry universal, sem expor segredos.\n"
    )

    for tag in sorted(by_tag):
        items = by_tag[tag]
        add(f"## `{tag}` — {len(items)}\n")
        add("| Método | Rota | Descrição |")
        add("| --- | --- | --- |")
        for path, methods, desc in sorted(items):
            add(f"| `{methods}` | `{path}` | {desc} |")
        add("")

    add("## WebSockets\n")
    add("| Rota | Descrição |")
    add("| --- | --- |")
    for path, desc in sorted(sockets):
        add(f"| `{path}` | {desc} |")

    return "\n".join(out) + "\n"


if __name__ == "__main__":
    sys.stdout.write(render())
