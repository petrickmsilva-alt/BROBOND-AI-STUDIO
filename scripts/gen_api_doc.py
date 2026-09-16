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
        "para health/capabilities do registry universal, sem expor segredos. PR008 "
        "adiciona seis rotas `/api/v1/render/*` (lotes de render com identidade) e o "
        "WebSocket `/ws/render/{batch_id}` com progresso por push, sem polling. "
        "V3.1 adiciona doze rotas `/api/v1/graph/*` (Cinematic Knowledge Graph "
        "com identidade: CRUD de nós/arestas, busca semântica, vizinhança e "
        "contexto de personagem para o Director AI). V3.2 adiciona treze rotas "
        "`/api/v1/continuity/*` (Character Continuity Engine com identidade: "
        "cinco locks com fingerprint, resolver persona+campanha+episódio e "
        "histórico imutável de episódios). V3.3 adiciona sete rotas "
        "`/api/v1/campaigns/*` (Campaign Builder com identidade: interpretar "
        "um briefing, criar a campanha completa com sete entregáveis e "
        "timeline de cinco dias, duplicar, anexar entregas reais e exportar "
        "o ZIP com manifesto).\n"
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

    # V3.2.1: how the CLIENT reaches these routes. Pure prose — the inventory
    # above remains the canonical, generated route list.
    add("")
    add("## Cliente — camada de rede (V3.2.1)")
    add("")
    add("Todas as chamadas acima partem de `lib/api.ts`, que delega a `lib/network/request.ts` —")
    add("a única fronteira de `fetch` do frontend. Timeout 10s (30s em upload), trace id")
    add("`x-brobond-trace`, e retry **somente GET** para as três sondas de status")
    add("(`/api/v1/health`, `/api/v1/system/readiness`, `/api/v1/system/gpu`: 3 tentativas,")
    add("backoff 300/600/1200ms). Falhas chegam tipadas (`NetworkErrorType`) e timeout na janela")
    add("8–60s é tratado como cold start (\"Servidor iniciando…\"), não como API Offline.")
    add("Nenhuma rota nova — este documento continua sendo o inventário canônico")
    add("(106 rotas HTTP + 3 WebSockets). Detalhes: `docs/NETWORK_LAYER.md`.")

    return "\n".join(out) + "\n"


if __name__ == "__main__":
    sys.stdout.write(render())
