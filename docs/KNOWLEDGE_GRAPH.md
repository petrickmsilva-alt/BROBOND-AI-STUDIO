# Cinematic Knowledge Graph (V3.1)

Personagens, marcas, campanhas, lugares, veículos, figurino e objetos — e as
relações entre eles — num grafo persistente por workspace, com busca
semântica PT/EN e contexto de personagem para o Director AI.

O Director AI, o Provider Registry e o Render Engine não foram alterados: o
grafo **enriquece**, nunca reescreve, o `GenerationSpec`.

---

## Modelo

Duas tabelas (migração Alembic `0003`), sem foreign keys no banco — a mesma
convenção portátil SQLite/Postgres de personas (PR003):

| Tabela | Conteúdo |
|---|---|
| `graph_nodes` | um entity: `entity_type`, `name`, `slug` (único por workspace), `attributes`/`aliases` em JSON |
| `graph_edges` | uma relação dirigida: `source_id` → `relation` → `target_id`, sempre no vocabulário canônico |

Sete tipos de entidade, todos relacionáveis com todos: `character`, `brand`,
`campaign`, `location`, `vehicle`, `wardrobe`, `prop`.

Todo acesso é **escopo de workspace**: id estrangeiro responde **404**, nunca
403, para ids de outro tenant não serem enumeráveis. Deletar um nó remove
suas arestas incidentes nas duas direções; deletar uma aresta não toca os nós.

---

## Vocabulário de relações

16 relações canônicas (armazenadas) + aliases PT/EN (normalizados na escrita):

| Canônica | Inversa | PT | EN |
|---|---|---|---|
| `drives` | `driven_by` | dirige | drives |
| `wears` | `worn_by` | veste | wears |
| `owns` | `owned_by` | possui | owns |
| `belongs_to` | `includes` | pertence a | belongs to |
| `located_at` | `hosts` | fica em | is located at |
| `part_of` | `contains` | é parte de | is part of |
| `features` | `featured_in` | apresenta | features |
| `produces` | `produced_by` | produz | produces |
| `manages` | `managed_by` | gerencia | manages |
| `collaborates_with` | `collaborates_with` | colabora com | collaborates with |
| `inspired_by` | `inspires` | se inspira em | is inspired by |
| `uses` | `used_by` | usa | uses |
| `designed_by` | `designed` | tem design de | is designed by |
| `styled_by` | `styled` | tem styling de | is styled by |
| `filmed_at` | `location_of` | tem locação em | was filmed at |
| `appears_in` | `shows` | aparece em | appears in |

Verbo fora do vocabulário é **422**, nunca aresta em texto livre. As frases
(`Petrick dirige RAM`) usam sempre a voz ativa a partir da fonte real da
aresta — relações de entrada nunca precisam de particípio flexionado.

---

## Busca semântica

`SemanticQuery` responde "RAM branca" com o Vehicle e "Showroom" com o
Location — sem embedding, sem LLM, sem rede. Matching com fold de acentos e
caixa sobre nomes, aliases e chaves/valores de atributos, em tiers
explícitos (`matched_fields` diz quais campos contribuíram):

| Pontos | Regra |
|---|---|
| 100 | igual ao nome |
| 95 | igual a um alias |
| 80 | nome começa com a busca |
| 75 | alias começa com a busca |
| 70 | todos os tokens no nome |
| 55 | todos os tokens no perfil (nome + aliases + atributos) |
| 40 | um token substring do nome |
| 30 | um token em aliases ou atributos |

Filtro `entity_type` explícito soma bônus +5 (teto 100). Empates desempatam
por nome, depois id: a ordem é estável entre processos e restarts.

---

## Travessia e contexto de personagem

- `RelationshipEngine.neighbors(node, depth=1–3, direction=out/in/both)`:
  BFS cycle-safe, ordem determinística (vizinhos por nome, arestas por
  relação). Nó desconhecido devolve subgrafo vazio com centro `None` — a rota
  decide o 404.
- `CharacterGraph.context(nome)`: encontra o `character` por nome, slug ou
  alias (sem acentos) e devolve relações (direção + peer + frase), frases
  ordenadas únicas (teto 25) e contagens por relação.
- `MemoryResolver.context_phrases(persona_id)` (ETAPA 5): o resolver composto
  com um `GraphContextSource` serve as frases do grafo para uma persona; sem
  source, devolve vazio — o grafo de chamadas pré-V3.1 comporta-se igual, e o
  resolver global continua sem source de grafo.

---

## Rotas (`tag graph`, todas com identidade)

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/v1/graph/nodes` | cria nó (201; 409 slug tomado; 422 vocabulário) |
| `GET` | `/api/v1/graph/nodes` | lista (filtro `entity_type`, paginação) |
| `GET` | `/api/v1/graph/nodes/{id}` | lê um nó (404 estrangeiro) |
| `PATCH` | `/api/v1/graph/nodes/{id}` | atualiza parcial (slug imutável) |
| `DELETE` | `/api/v1/graph/nodes/{id}` | remove nó + arestas (204) |
| `POST` | `/api/v1/graph/edges` | relaciona dois nós (verbo normalizado; 404 ponta ausente; 409 duplicada) |
| `GET` | `/api/v1/graph/edges` | lista (filtros `source_id`/`target_id`/`relation`) |
| `DELETE` | `/api/v1/graph/edges/{id}` | remove aresta (204; nós intactos) |
| `GET` | `/api/v1/graph/query?q=` | busca semântica ranqueada |
| `GET` | `/api/v1/graph/neighbors/{id}` | vizinhança (`depth` 1–3, `direction`) |
| `GET` | `/api/v1/graph/characters/{nome}/context` | identidade + relações + frases (200 com `found`) |
| `POST` | `/api/v1/graph/seed` | demonstração idempotente (9 nós, 11 arestas) |

Cada mutação escreve audit (`graph.node/edge.created/updated/deleted`,
`graph.seeded`). O inventário completo e gerado está em `docs/API.md`.

---

## Demonstração

`POST /api/v1/graph/seed` carrega o grafo do brief — Petrick dirige a RAM,
veste a Legacy Jacket; Legacy pertence a BroBond; Showroom fica em Goiânia —
mais campanha, lugares, veículo, figurino e objeto para cobrir os 7 tipos.
Slugs e relações existentes são pulados, nunca duplicados.

---

## UI `/studio/knowledge`

Canvas SVG com layout radial determinístico (`lib/graph/layout.ts`, puro e
testado em 100%), busca semântica, filtros por tipo com contagens, detalhe
com atributos/aliases/vizinhança e — para personagens — o contexto que o
Director AI recebe. Estados honestos: carregando, offline, vazio (com botão
de demonstração) e contagens vindas da API.

---

## Arquivos

| Arquivo | Responsabilidade |
|---|---|
| `backend/app/graph/graph_models.py` | ORM + vocabulário de tipos + JSON/slug |
| `backend/app/graph/relationship_engine.py` | vocabulário, BFS, frases, `CharacterGraph` (stdlib-only) |
| `backend/app/graph/semantic_query.py` | busca em tiers (stdlib-only) |
| `backend/app/graph/graph_repository.py` | persistência + adapter `RepositoryGraphStore` + seed |
| `backend/app/core/contracts.py` | `GraphContext`/`GraphContextSource` (aditivo) |
| `backend/app/core/memory_resolver.py` | `context_phrases()` (injeção opcional) |
| `alembic/versions/0003_knowledge_graph.py` | tabelas do grafo |
| `app/studio/knowledge/page.tsx` | UI do grafo |
| `lib/graph/layout.ts` | layout radial + cores + labels (puro) |
| `backend/tests/test_graph_*.py` | 201 testes (models, engine, search, repository, memory, api) |

**Verificar:**

```bash
PYTHONPATH=backend pytest backend/tests/test_graph_models.py backend/tests/test_graph_repository.py \
  backend/tests/test_relationship_engine.py backend/tests/test_semantic_query.py \
  backend/tests/test_graph_memory.py backend/tests/test_graph_api.py -q
PYTHONPATH=backend python scripts/gen_api_doc.py | grep -c 'api/v1/graph'  # 12
npm run test:frontend:coverage  # lib/graph/layout.ts em 100%
```
