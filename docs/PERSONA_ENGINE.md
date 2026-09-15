# Persona Memory Engine (PR003)

As personas do produto deixaram a memória do processo e passaram a viver em
PostgreSQL, preservando 100% da arquitetura: o Core continua framework-free,
nenhuma tabela existente foi tocada, nenhum arquivo foi deletado e todos os
contratos de request/response anteriores se mantêm.

- **Spec:** `PR003.md` (pasta do pedido)
- **Testes:** `backend/tests/test_persona_engine.py` (19 testes)
- **Estado:** entregue; suíte 1.143 testes, cobertura ≥ 95%, build aprovado

## O que mudou, em uma frase

`POST /api/v1/personas` e a tela `/studio/personas` criam **linhas** nas
tabelas `personas` / `persona_images` / `persona_wardrobe` /
`persona_identity_revision` (Alembic `0002`), e o `MemoryResolver` — que o
`GenerationSpecBuilder` já usava — agora resolve essas linhas por injeção,
sem importar SQLAlchemy.

## Diagrama de dependência

```text
Rotas /api/v1/personas/*        Rotas /api/v1/generations/*
        │ (current_user)                 │ (persona_id opcional no request)
        ▼                                ▼
repositories/persona_repository.py    _generation_parameters()
  create/update/delete/find_*/        (herda persona.lora_id → job.parameters)
  list_workspace + to_memory/to_profile         │
        ▲                                       ▼
        │                    MemoryResolver ──► GenerationSpecBuilder
        │              resolve()      (identidade p/ prompt + default_style)
        │              resolve_persona() (perfil completo)
        └── adapters em main.py (composition root):
            _CompositePersonaSource          (fetch: DB → fallback ledger)
            _PersistentPersonaProfileSource  (get_profile: DB)
```

**O Core não toca SQL.** Os dois adapters vivem em `main.py`;
`memory_resolver.py` e `contracts.py` só conhecem dataclasses e protocols
(guarda: `test_core_independence.py` + `test_docs_accuracy.py`).

## Schema (Alembic `0002_persona_engine`)

| Tabela | Colunas | Notas |
| --- | --- | --- |
| `personas` | `id` UUID pk, `workspace_id`, `name`, `slug`, `age`, `height`, `body_type`, `skin_tone`, `hair`, `beard`, `eyes`, `voice`, `default_style`, `lora_id` (nullable), `revision`, `created_at`, `updated_at` | `uq_personas_workspace_slug` — slug único **por workspace** (409 na API). `knowledge_entries` (listada na spec) já existia na baseline `0001`, com guard idempotente |
| `persona_images` | `id`, `persona_id`, `asset_id`, `image_type` (face/body/style/reference), `order_index` | `asset_id` **sem FK**: o fluxo legado de treino referencia assets criados depois; a validação de existência vive na rota `/images` (404/422) |
| `persona_wardrobe` | `id`, `persona_id`, `name`, `category`, `metadata` (JSON em Text) | Convenção SQLite/Postgres-portável, idêntica a `audit_log.detail` |
| `persona_identity_revision` | `id`, `persona_id`, `revision`, `notes` (JSON), `created_by`, `created_at` | Append-only: criação = revisão 1; cada mudança de identidade appende (nunca reescreve) |

A migration é idempotente (tabela/index existentes → skip) e o `downgrade` é
**no-op documentado**: a Regra de Ouro (Bible §2) proíbe drop de tabelas
históricas e a linha de persona é dado de produto.

## Contratos novos no Core

| Símbolo | Papel |
| --- | --- |
| `WardrobeItem` | `name` + `category` + `metadata` (dict livre, o produto interpreta) |
| `ReferenceImage` | `asset_id` + `image_type` + `order_index` |
| `PersonaProfile` | `identity: PersonaMemory` + `wardrobe` + `lora_id` + `reference_images` |
| `PersonaProfileSource` (protocol) | `get_profile(persona_id) -> PersonaProfile \| None` |
| `MemoryResolver.resolve_persona(id)` | Perfil completo; sem fonte de perfil, deriva da identidade (ledger/seed) — comportamento pré-PR003 intacto |

`PersonaSource` (`fetch`/`search`) **não mudou** — `PersonaLedger`,
`SeedPersonaSource` e os fakes de teste continuam válidos.

## Endpoints (todas `Depends(current_user)`, externas → 404)

| Método | Rota | Comportamento |
| --- | --- | --- |
| `POST` | `/api/v1/personas` | Contrato original (202, `Persona`) — agora **persiste** perfil + referências + revisão 1. Slug duplicado no workspace → 409 |
| `GET` | `/api/v1/personas` | Lista os perfis do workspace (wardrobe, imagens, revisões) |
| `GET` | `/api/v1/personas/{id}` | Perfil completo; `name`/`url` do asset quando ele ainda existe |
| `PATCH` | `/api/v1/personas/{id}` | Parcial (`exclude_unset`); identidade → `revision += 1` + linha de histórico; `wardrobe` substitui o guarda-roupa; slug estável |
| `DELETE` | `/api/v1/personas/{id}` | 204; remove perfil + filhas; assets e `training_runs` permanecem |
| `GET` | `/api/v1/personas/{id}/images` | Referências ordenadas por `order_index` |
| `POST` | `/api/v1/personas/{id}/images` | 201; asset deve existir no workspace e ser `kind=image` (senão 404/422); duplicado → 409. **Sem upload** — o upload continua no fluxo de assets |

Campos de identidade (bump de revisão): `name`, `age`, `height`,
`body_type`, `skin_tone`, `hair`, `beard`, `eyes`, `voice`. Metadados (sem
bump): `default_style`, `lora_id`, `wardrobe`.

## Como a persona chega na geração

1. `ImageGenerationRequest`/`VideoGenerationRequest` ganham `persona_id`
   **opcional** (request sem ele se comporta exatamente como antes).
2. `_generation_parameters` herda `persona.lora_id` em `job.parameters`
   (LoRA explícito no request vence). O worker já resolve asset → path com
   checagem de workspace — o mesmo caminho dos LoRAs selecionados no UI,
   então `spec.lora` nunca carrega id cru.
3. `spec_adapter` passa `persona_id` ao `GenerationSpecBuilder`, que resolve
   via `MemoryResolver` → `PersonaMemory` (identidade aprovada) → a frase de
   identidade e o `default_style` entram no prompt compilado.
4. `persona_repo.to_memory` mapeia a linha para o Core: `lora_path` fica
   `None` de propósito (LoRA via parâmetro, acima); `version` = `revision`.

## Privacy

Personas persistidas são **dado de tenant**: `find_by_id(..., workspace_id=…)`
em todas as rotas e 404 (não 403) para ids externos. O catálogo global
`GET /core/personas` continua listando apenas personagens do ledger — o
`search` do composite é propositalmente privado.

## O que é Legacy (marcado, nunca deletado)

- `app/store.py` → `_PersonaMemory`/`Store.personas`/`add_persona`: sem call
  sites desde o PR003 (a fonte de verdade é a tabela `personas`).
- `PersonaMemoryEngine`/`PersonaLedger` (Core): permanecem a governança dos
  **personagens** do produto (revisar/aprovar/retratar + episódios) — as
  personas do perfil são um caminho separado e mais simples, por desenho.

## Próximos passos sugeridos

- **PR004 — Personas no pipeline de geração do estúdio:** campo "persona" na
  tela de Image/Video Studio que preenche `persona_id` (o backend já suporta),
  pré-visualização da identidade compilada via `/core/compile` e seleção do
  LoRA treinado do perfil (`/personas/{id}/loras`).
- `Skin tone`/`height` já persistem; o prompt de identidade pode evoluir para
  usá-los explicitamente (hoje a frase usa idade/altura/corpo/cabelo/barba/
  olhos — a foto de referência carrega o resto).
- Exclusão de imagem individual (`DELETE /personas/{id}/images/{image_id}`)
  para gerenciar o acervo sem reanexar tudo.
