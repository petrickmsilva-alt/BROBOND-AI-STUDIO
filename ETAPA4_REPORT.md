# RELATÓRIO TÉCNICO — ETAPA 4: PERSONA MEMORY ENGINE

**Repositório:** `petrickmsilva-alt/BROBOND-AI-STUDIO`
**Branch:** `arena/01a0a25e-brobond-ai-studio`
**Data:** 2026-09-14
**Escopo:** apenas a ETAPA 4. Nenhuma etapa posterior foi iniciada.

---

## 1. Objetivo

Tornar a memória de personagem **permanente, versionada e governada**, de modo que:

- identidade nunca mude em silêncio;
- toda alteração tenha autor, motivo e carimbo de tempo;
- episódios já publicados mantenham o snapshot de identidade com que foram feitos;
- seja possível responder "o que mudou neste personagem e quando?" sem depender de memória humana.

---

## 2. Auditoria do ponto de partida

Antes de escrever código, medi o que a ETAPA 2 já entregava em
`backend/app/core/memory_resolver.py` (179 linhas):

| Capacidade | Estado antes da ETAPA 4 |
| --- | --- |
| Resolver identidade por id / nome | ✅ `resolve`, `resolve_by_name` |
| Bloco de prompt PERSONA | ✅ `identity_phrase` |
| Regra de autorização de mudança | ✅ `revise(authorized=…)` |
| `version + 1` em mudança de identidade | ✅ |
| **Histórico persistido** | ❌ **não existia** |
| **Recuperar a versão N** | ❌ impossível |
| **Snapshot vinculado a episódio** | ❌ `snapshot()` existia mas nada o guardava |
| **Fluxo de aprovação** | ⚠️ apenas via `revise(status=…)`, sem ator nem motivo |
| **Relatório de drift** | ❌ não existia |

**Conclusão da auditoria:** `revise()` devolvia um `PersonaMemory` com `version + 1` e a
identidade anterior era simplesmente descartada. A regra publicada em
`knowledge_base/CHARACTER_LIBRARY.md` — *"A character edit creates a new version. Existing
episodes keep their original memory snapshot."* — era, até aqui, **inverificável**: nada
registrava snapshot algum.

Segunda constatação: os personagens estavam definidos em **três lugares**
(`memory_resolver.SEED_PERSONAS`, `knowledge.py:SEEDS`, `CHARACTER_LIBRARY.md`). Criar uma
quarta cópia seria um risco de divergência, então o engine **consome** `SEED_PERSONAS` em vez
de redeclarar.

---

## 3. Decisões de projeto

### 3.1 Composição, não reimplementação

`PersonaMemoryEngine` **não** reimplementa vocabulário nem a regra de autorização. Ele
delega a `MemoryResolver`:

```python
def identity_phrase(self, persona_id, *, version=None) -> str:
    return self.memory.identity_phrase(self.resolve(persona_id, version=version))
```

Existe exatamente **uma** definição de cada regra. O teste
`test_the_engine_delegates_vocabulary_instead_of_reimplementing_it` compara as saídas dos
dois objetos para impedir que alguém as separe depois.

### 3.2 `PersonaLedger` como fonte única

O ledger implementa o `Protocol` `PersonaSource` — a costura que `memory_resolver.py`
declarou na ETAPA 2 ("*ETAPA 4 can swap the seed source for PostgreSQL without touching this
file*"). Em `main.py`:

```python
persona_ledger = PersonaLedger()
persona_engine = PersonaMemoryEngine(ledger=persona_ledger)
memory_resolver = MemoryResolver(persona_ledger)
```

Consequência arquitetural importante: **engine e `GenerationSpecBuilder` leem o mesmo
histórico**. Um personagem aprovado pela API fica imediatamente utilizável pelo compilador,
sem fiação adicional. Isso é coberto por `test_an_approved_persona_reaches_a_generation_spec`.

### 3.3 `revision` ≠ `version`

Dois contadores, porque são duas coisas:

- `version` — versão de **identidade**. Só sobe em mudança de rosto/corpo/cabelo/roupa/voz.
  Semântica herdada da ETAPA 2 e **preservada** (testes antigos dependem dela).
- `revision` — sequência do ledger. Sobe em **toda** escrita, inclusive administrativa.

`fetch_version(id, n)` devolve a última revisão que carrega aquela versão de identidade —
ou seja, o estado que o personagem efetivamente apresentava.

### 3.4 Aprovação exige definição, nunca a fornece

```python
if not _is_defined(persona):
    raise MemoryError_(
        f"{persona_id} has no defined identity; approval requires definition, it never supplies it"
    )
```

Esta é a proteção contra fabricar personagem. `CHAR_JEFFERSON` continua `planned`, sem
atributos, e `approve()` **recusa** promovê-lo — a API responde 409. Nenhum atributo foi
inventado em lugar nenhum.

---

## 4. O que foi implementado

| Arquivo | Status | Conteúdo |
| --- | --- | --- |
| `backend/app/core/persona_memory.py` | **novo, 405 l** | `PersonaVersion`, `PersonaLedger`, `PersonaMemoryEngine`, `PersonaNotFound` |
| `backend/app/core/__init__.py` | alterado | 5 exports novos; docstring atualizada (seis → sete componentes) |
| `backend/app/schemas.py` | alterado | 5 schemas novos, com validação de campos |
| `backend/app/main.py` | alterado | ledger como fonte única + 8 rotas que só delegam |
| `backend/tests/test_core_persona_memory.py` | **novo, 406 l** | 36 testes de engine |
| `backend/tests/test_core_persona_api.py` | **novo, 273 l** | 24 testes de HTTP |

### Regras garantidas por teste

| Regra | Teste |
| --- | --- |
| Mudança de identidade sem autorização é rejeitada | `test_identity_change_without_authorization_is_rejected` |
| Uma mudança rejeitada **não** entra no histórico | idem (afirma `len(history) == 1`) |
| Todo write tem ator e motivo obrigatórios | `test_actor_and_reason_are_mandatory_on_every_write` |
| Personagem novo nasce `planned` | `test_a_new_character_is_planned_until_approved` |
| Aprovação exige identidade definida | `test_approval_refuses_an_undefined_identity` |
| Edição administrativa não sobe `version` | `test_administrative_changes_do_not_bump_the_identity_version` |
| Versões antigas permanecem recuperáveis | `test_previous_identity_versions_stay_retrievable` |
| Episódio mantém o snapshot original | `test_an_episode_keeps_its_original_snapshot` |
| Ausência de snapshot ≠ consistência | `test_continuity_distinguishes_missing_from_consistent` |
| `drift` reporta só identidade, não churn | `test_drift_names_what_changed_and_when` |
| Seeds não são duplicados | `test_seeds_are_not_duplicated_by_the_ledger` |
| Rotas não decidem regra de identidade | `test_the_persona_routes_contain_no_identity_logic` |

### Superfície HTTP (8 rotas novas, todas sob `core`)

```
GET  /api/v1/core/personas
GET  /api/v1/core/personas/{persona_id}
POST /api/v1/core/personas/{persona_id}/revise
POST /api/v1/core/personas/{persona_id}/approve
POST /api/v1/core/personas/{persona_id}/retire
POST /api/v1/core/personas/{persona_id}/episodes/{episode_id}/snapshot
GET  /api/v1/core/personas/{persona_id}/episodes/{episode_id}/memory
GET  /api/v1/core/personas/{persona_id}/continuity
```

Mapeamento de erro: `PersonaNotFound` → **404**, `MemoryError_` → **409**, validação de
schema → **422**. `PersonaNotFound` é subclasse de `MemoryError_`, então handlers existentes
continuam funcionando.

---

## 5. Verificação

| Verificação | Antes | Depois |
| --- | --- | --- |
| `pytest backend/tests -q` | 222 passed | **282 passed** |
| Ordem inversa dos arquivos | — | **282 passed** |
| Os 22 testes originais, isolados | 22 passed | 22 passed |
| Cobertura de `core/persona_memory.py` | — | **100%** (151 stmts, 0 miss) |
| Cobertura de `backend/app/core/` | 95% | **96%** |
| Cobertura total `backend/app` | 75% | **78%** |
| `npm run build` | ✓ | ✓ Compiled successfully |
| Rotas `/api/v1` | 29 | **37** (+8) |
| **Rotas removidas** | — | **nenhuma** |

O inventário de rotas foi conferido por diff contra o baseline pré-Core (HTTP + WebSocket,
30 entradas): **0 removidas, 10 adicionadas** (2 da ETAPA 2 + 8 desta).

### Dois defeitos que os próprios testes pegaram

1. **`field(default_factory=dict)` em classe comum.** Declarei `_episodes` no fim da classe
   como se fosse dataclass; isso produziria um objeto `Field` compartilhado entre instâncias,
   não um dicionário. Corrigido para inicialização em `__init__`.
2. **`drift()` contradizia o próprio docstring.** Dizia "identity fields" mas incluía
   `lora_path`, misturando churn administrativo com deriva de identidade. O código foi
   corrigido para filtrar por `PERSONA_IDENTITY_FIELDS`; o histórico continua registrando tudo.

Também corrigi uma expectativa errada minha (tentava re-aprovar `CHAR_PETRICK`, que já nasce
aprovado) e duas suposições sobre o formato da resposta HTTP.

### Isolamento de estado

`persona_engine` é singleton de módulo. Todos os testes de HTTP rodam contra um ledger
descartável injetado por fixture autouse. Verificado: após a suíte inteira, o ledger global
continua com 1 revisão e `CHAR_PETRICK` com `dark brown eyes`. A suíte passa nas duas ordens
de arquivo.

---

## 6. Explicitamente NÃO feito nesta etapa

- **Persistência em PostgreSQL continua aberta.** O ledger é em memória; um processo reiniciado
  perde o histórico. A costura (`PersonaSource`) está pronta e testada
  (`test_the_persona_source_protocol_is_structural_not_nominal` mostra que qualquer objeto com
  `fetch`/`search` serve), mas a migração em si não foi feita.
- **Episódios também não são persistidos.** `remember`/`recall` vivem no mesmo processo.
- **Sem autenticação nas rotas novas.** Seguem o padrão das rotas `/core/*` existentes, que
  também são abertas — o P0-4 da auditoria permanece.
- **Nenhum personagem novo foi inventado.** `CHAR_JEFFERSON` continua `planned` e sem atributos.
- A UI não consome essas rotas ainda (ETAPA 15).
- `hub.publish` segue sem chamadores (P0-3).

---

## 7. Riscos e recomendação

| Risco | Mitigação já aplicada |
| --- | --- |
| Divergência entre engine e resolver | Fonte única (`PersonaLedger`) injetada nos dois |
| Quarta cópia dos seeds | Engine consome `SEED_PERSONAS`; teste impede duplicação |
| Estado de teste vazando para outros arquivos | Fixture autouse + verificação pós-suíte |
| Regra de identidade duplicada em rota | Teste de guarda inspeciona o fonte das 8 rotas |
| Confusão `revision` × `version` | Docstrings + teste que fixa `[1, 1, 2, 2]` |

**Recomendação para a próxima etapa:** a ETAPA 5 (Cinematic Library) é aditiva e independente.
Mas a persistência do `Job` (P0-2b) e a do ledger agora são os dois únicos bloqueadores de
uma geração real ponta a ponta em produção — vale priorizá-los antes de acumular mais camadas
sobre memória volátil.
