# Cinematic Knowledge Graph (V3.1)

A memória de personagem virou conhecimento relacional: o que antes só existia
como texto na Character Library agora é um **grafo persistente** — Character,
Brand, Campaign, Location, Vehicle, Wardrobe e Prop, todas relacionáveis, com
relações bidirecionais, busca semântica determinística e uma tela de mapa.

- **Spec:** sprint V3.1 (etapas 1–7)
- **Código:** `backend/app/graph/` (`graph_models.py`, `graph_repository.py`,
  `relationship_engine.py`, `semantic_query.py`) + migration Alembic `0003`
- **Testes:** `backend/tests/test_graph_repository.py`,
  `test_graph_relationship_engine.py`, `test_graph_semantic_query.py`,
  `test_graph_api.py`, `test_graph_memory_integration.py` — pacote `graph/` a
  100% de cobertura
- **Estado:** entregue; suíte 1.495 testes, cobertura 97% (gate CI: 95%),
  build aprovado. Director AI, Provider Registry e Render Engine **intactos**.

## O que mudou, em uma frase

O grafo vive em duas tabelas (`knowledge_graph_nodes`,
`knowledge_graph_relationships`); o catálogo canônico do BROBOND (Petrick
`dirige` a RAM branca, `veste` a Legacy Jacket; a coleção Legacy `pertence` à
BroBond; o Showroom `localizado` em Goiânia) fica no workspace `global`
somente leitura; os nós do workspace sobrepõem e estendem o catálogo; e o
`MemoryResolver` passou a expor `knowledge_context(persona_id)` —
**apenas contexto**, com o `GenerationSpec` de 19 campos intacto.

## Diagrama de dependência

```text
Rotas /api/v1/graph/*                  /api/v1/core/personas/{id}/knowledge-context
        │ (current_user)                          │ (current_user)
        ▼                                         ▼
graph_repository.py (graph_repo)        memory_resolver.knowledge_context()
  CRUD + views + seed canônico               │ (KnowledgeContextSource, por injeção)
        ▲                                    ▼
        │                    _GraphKnowledgeContextSource (main.py)
        │                      resolve external_ref (CHAR_PETRICK → nó)
        ▼                                    │
relationship_engine.py ◄─────────────────────┘
  vocabulário (rótulo + reverso), validação, neighbors bidirecionais,
  shortest_path (BFS), seed_canonical
semantic_query.py
  pontuação determinística → entidade COMPLETA (nó + atributos + relações)

Tabelas (Alembic 0003): knowledge_graph_nodes, knowledge_graph_relationships
Catálogo: workspace_id = "global" (read-only)  ·  Workspace: nós + relações próprios
```

**O Core não toca SQL.** O bridge e os adapters vivem em `main.py`;
`memory_resolver.py` e `contracts.py` só conhecem as dataclasses congeladas
`KnowledgeEntity` / `KnowledgeRelation` / `KnowledgeContext` e o protocolo
`KnowledgeContextSource` (guardas: `test_core_independence.py`,
`test_core_contracts.py` — o `GENERATION_SPEC_FIELDS` continua com 19).

## As sete entidades, todas relacionáveis

`character`, `brand`, `campaign`, `location`, `vehicle`, `wardrobe`, `prop`.
O vocabulário de relações é uma **sugestão** com pares típicos, nunca uma
restrição — qualquer par de tipos é legal (`test_every_entity_type_is_relatable_to_every_other`
varia os 42 pares). Tipos fora do vocabulário são aceitos e lidos com o par
genérico `relacionado a`.

| relação | leitura do fonte | leitura do alvo | típico |
| --- | --- | --- | --- |
| `dirige` | dirige | é dirigido por | character → vehicle |
| `veste` | veste | é vestida por | character → wardrobe |
| `pertence` | pertence a | possui | campaign/wardrobe → brand |
| `localizado` | localizado em | contém | location → location |
| `aparece_em` | aparece em | apresenta | character → campaign |
| `usa` | usa | é usado por | character → prop |
| `faz_parte_de` | faz parte de | compõe | wardrobe/prop → campaign |

Uma relação é **uma linha** no banco; a bidirecionalidade vem do rótulo de
reverso: `neighbors()` devolve a vizinhança com `outgoing`/`incoming`, cada
lado lido do seu ponto de vista. `shortest_path()` é BFS com teto de
profundidade sobre o grafo não direcionado (o UI poderá responder "como X
conecta com Y").

## Busca semântica — determinística, sem modelo

"RAM branca" → o **Vehicle completo** (atributos `modelo: RAM 1500`,
`cor: branca` + a relação recebida de Petrick). "Showroom" → o **Location**.
Pontuação transparente: nome exato 100, prefixo 55, substring 40, frase nos
atributos 25, tokens em nome (12), valores de atributo (15), chaves de
atributo (6) e descrição (8); normalização de acento (`Goiânia` = `goiania`)
e stopword list curta. Nada de LLM simulado — a mesma regra do DirectorAgent.
Frase desconhecida → lista vazia, nunca chute.

## Memory Resolver — o enriquecimento que não muda spec

- `MemoryResolver(source, profile_source, knowledge=None)` — parâmetro
  **opcional**; sem ele, o resolver é byte-a-byte o comportamento de antes.
- `knowledge_context(persona_id)` → `KnowledgeContext | None`: o personagem
  canônico (pelo `external_ref`, ex. `CHAR_PETRICK`), as relações ao redor e
  uma frase compacta ("Petrick Martins dirige RAM; … veste Legacy Jacket; …").
- Pessoa fora do catálogo → `None` (a rota responde 404, não 500).
- **`GenerationSpec` não foi tocado**: `test_knowledge_context_never_leaks_into_the_generation_spec`
  compila o mesmo prompt com e sem o grafo e exige igualdade campo a campo
  (só o `spec_id` difere, que é único por construção).

## API (11 rotas de grafo + 1 rota core, todas com identidade)

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/v1/graph` | Grafo completo (nós + relações + contagens por tipo e por relação) |
| `GET` | `/api/v1/graph/vocabulary` | Vocabulário de relações (para o picker da UI) |
| `GET` | `/api/v1/graph/nodes` | Nós visíveis, filtros `entity_type` e `q` |
| `POST` | `/api/v1/graph/nodes` | Cria nó do workspace (409 duplicado, 422 tipo inválido) |
| `GET` | `/api/v1/graph/nodes/{id}` | Nó + relações bidirecionais |
| `PATCH` | `/api/v1/graph/nodes/{id}` | Edita nó próprio (403 em canônico) |
| `DELETE` | `/api/v1/graph/nodes/{id}` | Remove nó próprio + relações incidentes |
| `GET` | `/api/v1/graph/relationships` | Relações visíveis, filtros por tipo/fonte/alvo |
| `POST` | `/api/v1/graph/relationships` | Cria relação (422 self-loop, 404 ponta ausente, 409 duplicata) |
| `DELETE` | `/api/v1/graph/relationships/{id}` | Remove relação própria (403 em canônica) |
| `GET` | `/api/v1/graph/search?q=` | Busca semântica → entidades completas |
| `GET` | `/api/v1/core/personas/{id}/knowledge-context` | Contexto relacional pelo Memory Resolver |

Isolamento de tenant: a vizinhança de um nó canônico compartilhado é sempre
`global + workspace do chamador` — a relação que outro workspace criou com a
RAM nunca aparece na sua busca (`test_relationships_for_node_returns_both_directions_scoped`).

## UI — `/studio/knowledge`

Canvas SVG com layout determinístico (clusters por tipo de entidade em anel;
nódulos opacos = catálogo, translúcidos = seus), arestas com seta e rótulo da
relação, busca semântica com resultados completos (score + descrição +
atributos), filtros por tipo (chips) e por relação, painel do nó com
atributos, relações nas duas direções (→ rótulo, ← reverso), criação de
relação (tipo + destino) e remoção de nós/relações próprios. Sem biblioteca
de grafo — o layout é aritmética simples e estável entre renders.

## O que isso **não** é

- Não é um RAG e não carrega/embedding de vetor: a busca é lexical
  determinística, explicável e testável.
- Não altera o fluxo de geração: o worker continua compilando o spec do
  mesmo jeito; o contexto do grafo é exposto para a UI e para a rota core.
- Não é multi-tenant: segue o escopo de workspace existente (um token, um
  workspace + o catálogo global).
