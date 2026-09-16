# BROBOND AI STUDIO — as 17 etapas

Índice do trabalho. Cada etapa teve **auditoria antes de implementação** e terminou com um
relatório técnico na raiz do repositório.

A regra que atravessou as 17: medir antes de afirmar. Quando uma hipótese se revelou falsa, o
relatório diz qual era e o que a medição mostrou — inclusive quando a hipótese errada era minha.

---

## Índice

| # | Etapa | Entrega principal | Relatório |
| --- | --- | --- | --- |
| 1 | **Auditoria** | 4 defeitos P0 catalogados; nada modificado | `AUDIT.md` |
| 2 | **BROBOND CORE** | camada de decisão em `backend/app/core/`, isolada de FastAPI | — |
| 3 | **GenerationSpec** | `GenerationSpec` v1.0 com 19 campos; `generate(spec, output_dir)` | — |
| 4 | **Persona Memory** | personas com revisão, aprovação, continuidade | `ETAPA4_REPORT.md` |
| 5 | **Cinematic Library** | lentes, iluminação, enquadramento, motivações; auditoria contra a Bíblia | `ETAPA5_REPORT.md` |
| 6 | **Shot Library** | 300 presets, 10 publicados, `audit()` | `ETAPA6_REPORT.md` |
| 7 | **Director AI** | intenção → direção; `detect_formats`, esclarecimento | `ETAPA7_REPORT.md` |
| 8 | **Storyboard Engine** | brief → shots reais com validação gramatical | `ETAPA8_REPORT.md` |
| 9 | **Prompt Compiler** | 12 blocos determinísticos, sem string solta | `ETAPA9_REPORT.md` |
| 10 | **Provider Adapters** | registry por provider pedido, não por tipo de job | `ETAPA10_REPORT.md` |
| 11 | **Queue / WebSocket** | `publish_sync`, marcos de progresso, evento terminal único | `ETAPA11_REPORT.md` |
| 12 | **Storage MinIO/S3** | `storage.py` cobrindo local e S3 pelo mesmo caminho | `ETAPA12_REPORT.md` |
| 13 | **Video Timeline** | timeline com transições, validação e `is_rendered` honesto | `ETAPA13_REPORT.md` |
| 14 | **Quality AI** | `QualityGate` confere o output antes de persistir | `ETAPA14_REPORT.md` |
| 15 | **UX Premium** | Diretor como porta de entrada; casca sem fatos inventados | `ETAPA15_REPORT.md` |
| 16 | **Testes 95%** | cobertura 89% → 95%; PR005 elevou o gate atual para `--fail-under=95` | `ETAPA16_REPORT.md` |
| 17 | **Documentação** | docs verificadas contra o código, com guarda anti-drift | `ETAPA17_REPORT.md` |

As etapas 2 e 3 não têm relatório próprio: foram as duas primeiras implementações, executadas
antes de o formato de relatório ser estabelecido na ETAPA 4. O que entregaram está em
`ARCHITECTURE.md` (seções "BROBOND CORE" e "Contrato de provider (ETAPA 3)").

---

## Os quatro defeitos P0 da auditoria original

| ID | Defeito | Estado |
| --- | --- | --- |
| **P0-1** | Dois backends paralelos; seis módulos mortos **e quebrados** | **Aberto por decisão** — 4 módulos, 100 statements que não importam. Não apagados (instrução permanente), não consertados (ressuscitariam um backend duplicado). Fronteira fixada por teste. Ver `docs/LIMITATIONS.md` §5 |
| **P0-2a** | `process_generation` devolvia sempre `cancelled` | **Corrigido na ETAPA 3** |
| **P0-2b** | `MemoryStore` em memória | **Fechado no PR002 e PR003** — jobs são linhas na tabela `jobs` (migration Alembic `0001`); `JobStore` é o repositório comum da API e do worker. Personas fechadas no PR003: tabela `personas` (migration `0002`) + `repositories/persona_repository.py`. Ver `docs/LIMITATIONS.md` §2 e `docs/PERSONA_ENGINE.md` |
| **P0-3** | `EventHub.publish` sem chamadores | **Corrigido na ETAPA 11** — `publish_sync`, porque o worker Celery é síncrono e o hub era asyncio-only |
| **P0-4** | Endpoints sem token; vazamento cross-tenant em `GET /api/v1/queue`; PII em `GET /api/v1/knowledge` | **Fechado no PR002 (ampliado no PR003, no PR008, na V3.1, na V3.2 e na V3.3)** — **66 de 106 rotas** exigem token, 3 o aceitam sem exigir (gerações + `/core/compile`), 37 permanecem públicas por desenho (dados de referência, `/api/v1/providers` e Core read-only, incluindo `/core/director/production-plan`); os 3 WebSockets autenticam por `?token=`; rate limit configurável em login/registro e audit log para ações críticas. Ver `docs/LIMITATIONS.md` §3 |

---

## Invariantes que atravessam as 17 etapas

Estas regras foram respeitadas em todas as etapas e são verificadas por testes:

1. **Zero arquivos deletados** desde o commit inicial `3708784`. Verificado por
   `git diff --diff-filter=D --name-only 3708784`.
2. **Nenhuma rota FastAPI contém lógica de IA.** Toda decisão vive em `backend/app/core/`.
   Verificado por análise AST em `test_core_api.py`.
3. **Todo provider recebe apenas `GenerationSpec`** — nunca prompt solto, nunca `dict` de
   parâmetros.
4. **O Core não importa framework.** Os **13** componentes top-level são livres de `fastapi`,
   `starlette`, `sqlalchemy`, `celery`, `boto3` e `pydantic_settings` — verificado por análise
   AST. A guarda `test_core_independence.py` lista **8** deles em `INDEPENDENT_MODULES`, porque
   ela afirma uma propriedade mais forte: importar **sem nenhum irmão do Core**. Os outros
   cinco (`cinematic_library`, `generation_spec_builder`, `persona_memory`, `shot_library`,
   `storyboard_engine`) compõem uns aos outros por desenho, então não satisfazem a propriedade
   mais forte embora satisfaçam a que importa. PR005 adiciona `core/director/`, também sem
   frameworks ou providers, como pacote de planejamento composto; PR006 acrescenta nele
   `StoryboardState`/`StoryboardHistory` para edição de plano, ainda sem providers. Medido,
   não presumido.
5. **Nada é inventado.** Nenhum arquivo, job concluído, modelo carregado ou output inexistente
   é afirmado. Quando algo não pôde ser verificado, o relatório diz isso explicitamente.
6. **Os 22 testes originais continuam passando**, sem modificação. Exceção registrada no
   PR002: `test_knowledge.py` passou a autenticar, porque o PR exige token em `GET /knowledge`
   (PII de personas) — os 2 testes do arquivo mantêm as mesmas asserções, agora com o header de
   identidade.

---

## Números atuais

| Métrica | Valor |
| --- | --- |
| Suíte de testes | **1.955** |
| Cobertura `backend/app` | **97%** (gate CI: 95%) |
| Módulos em 100% | **82** |
| Rotas HTTP `/api/v1` | **106** — **32** delas `/api/v1/core/*` |
| WebSockets | **3** |
| Componentes do Core | **13** |
| Arquivos deletados desde `3708784` | **0** |

Estes números são conferidos contra a aplicação em execução por
`backend/tests/test_docs_accuracy.py`.
