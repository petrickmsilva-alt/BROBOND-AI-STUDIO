# Character Continuity Engine (V3.2)

O mesmo personagem em qualquer episódio: identidade, figurino, locação,
veículo e voz congelados por campanha — com override por episódio,
fingerprint visual e histórico imutável de episódios.

O Director AI, o Provider Registry e o Render Engine não foram alterados: a
continuidade **enriquece** o contexto cinematográfico, nunca reescreve o
`GenerationSpec`.

---

## Modelo

Duas tabelas (migração Alembic `0004`), sem foreign keys no banco — a mesma
convenção portátil SQLite/Postgres de personas (PR003) e do grafo (V3.1):

| Tabela | Conteúdo |
|---|---|
| `continuity_locks` | um lock: `(workspace, persona, campanha, episódio, tipo)` → `payload` em JSON + `fingerprint` + `version` |
| `continuity_episodes` | um episódio congelado: `(workspace, persona, campanha, episódio)` → `snapshot` do resolver + título/notas |

Episódio `0` é o **padrão da campanha**: todo episódio o herda, a menos que
carregue seu próprio override. Episódios reais começam em `1`.

Todo acesso é **escopo de workspace**: id estrangeiro responde **404**, nunca
403, para ids de outro tenant não serem enumeráveis. Re-travar o mesmo escopo
substitui o payload e incrementa `version`; criar um episódio com número
repetido é **409**, porque um número de episódio é um endereço, não um
rascunho.

---

## Os cinco locks

Cada lock é um módulo framework-free em `backend/app/continuity/`, com um
snapshot congelado, validação, fingerprint, `verify` e uma frase
cinematográfica. O `identity_lock.py` hospeda ainda o kernel do pacote — o
erro `ContinuityValidationError`, o `fingerprint_for` canônico e a
normalização de chaves — para cada um existir exatamente uma vez.

| Lock | Módulo | Escopo | Congela |
|---|---|---|---|
| Identity | `identity_lock.py` | persona-global | rosto, cabelo, barba, corpo, pele, idade aparente (≥1 obrigatório) |
| Wardrobe | `wardrobe_lock.py` | campanha + override por episódio | roupa (obrigatória), acessórios, cores, sapatos, relógio |
| Location | `location_lock.py` | campanha + override por episódio | showroom, estúdio, rua (≥1 obrigatório), cidade, iluminação base |
| Vehicle | `vehicle_lock.py` | campanha + override por episódio | veículo + cor (obrigatórios), placa (opcional), rodas, acabamento |
| Voice | `voice_lock.py` | persona-global | perfil de voz (obrigatório), emoção padrão, velocidade, intensidade |

Identity e Voice são **persona-globais** (gravados sob a campanha `"default"`):
um personagem tem o mesmo rosto e a mesma voz em toda campanha, até que um
novo lock seja explicitamente gravado. Wardrobe, Location e Vehicle aceitam
`episode: null` (padrão da campanha) ou um número (override daquele episódio).

---

## Fingerprint visual

`fingerprint_for` é SHA-256 canônico truncado em 16 hex dos campos
normalizados (caixa e espaços laterais não movem o fingerprint; qualquer
outra mudança move). O separador `\x1f` impede colisão de fronteira entre
campos. Comparar dois episódios é comparar dezesseis caracteres:

```
wardrobe EP1 a1b2c3d4e5f60718
wardrobe EP2 a1b2c3d4e5f60718  → mesmo figurino
```

---

## Resolver

`ContinuityResolver.resolve(persona_id, campaign_id, episode)` devolve um
`ContinuityContext`: os cinco snapshots tipados (ou `None` onde nada está
travado), as frases, os fingerprints gravados, `missing`, `drift` e
`consistent`.

A leitura segue a cadeia de fallback — lock do episódio, padrão da campanha,
padrão persona-global — de modo que Identity/Voice resolvem em toda campanha
sem duplicação, enquanto Wardrobe/Location/Vehicle sobrescrevem por episódio.

`drift` lista locks cujo fingerprint gravado não reproduz mais o payload (a
linha foi editada fora de um lock write); `consistent` é verdadeiro apenas
sem faltas e sem drift. `block()` junta as frases em ordem fixa
(identity → wardrobe → location → vehicle → voice) para o bloco CONTINUITY
do prompt compilado — consumido explicitamente por quem pedir, nunca injetado
no `GenerationSpec`.

Sem store, todo lock é `missing`: um contexto vazio é válido, nunca um erro.
Persona em branco ou episódio inválido são recusados (`422`).

---

## Episódios

`POST /api/v1/continuity/episodes` congela o contexto resolvido naquele
instante — fingerprints, frases e payloads — sob o próximo número (max + 1,
ou explícito). Locks gravados depois **não alcançam** episódios passados: o
histórico é a verdade do que cada episódio usou.

---

## Rotas

Treze endpoints `/api/v1/continuity/*`, todos com identidade (`401` anônimo,
`404` para id estrangeiro ou lock ausente, `409` em episódio duplicado,
`422` em validação; cada mutação escreve audit):

| Método | Rota | Efeito |
|---|---|---|
| `PUT` | `/continuity/identity` | trava a identidade visual (persona-global) |
| `GET` | `/continuity/identity/{persona_id}` | lê a identidade travada |
| `PUT` | `/continuity/wardrobe` | trava o figurino (campanha ou episódio) |
| `GET` | `/continuity/wardrobe` | lê o figurino resolvido (+ `source_episode`) |
| `PUT` | `/continuity/location` | trava a locação (campanha ou episódio) |
| `GET` | `/continuity/location` | lê a locação resolvida (+ `source_episode`) |
| `PUT` | `/continuity/vehicle` | trava o veículo (campanha ou episódio) |
| `GET` | `/continuity/vehicle` | lê o veículo resolvido (+ `source_episode`) |
| `PUT` | `/continuity/voice` | trava a voz (persona-global) |
| `GET` | `/continuity/voice/{persona_id}` | lê a voz travada |
| `GET` | `/continuity/resolve` | um `ContinuityContext` (persona + campanha + episódio) |
| `POST` | `/continuity/episodes` | congela um novo episódio |
| `GET` | `/continuity/episodes` | lista episódios congelados (filtros opcionais) |

---

## UI `/studio/continuity`

Escopo (persona/campanha/episódio) + cinco cards de lock (ver, editar,
fingerprint, versão, origem) + painel do contexto resolvido (frases,
fingerprints, faltas, drift, selo consistente/incompleto) + histórico de
episódios com **Criar novo episódio**. Erros distinguem offline (`API
offline`), anônimo (`401` → "entre com sua conta") e rejeição do backend.

---

## Testes

200 testes novos (`test_continuity_*.py`, 4 arquivos): locks (validação,
fingerprint, verify, frases, round-trip), resolver (store fake: fallback,
missing, drift, bloco), repositório (upsert, versionamento, cadeia de
fallback, isolamento de workspace, episódios) e API (13 rotas: códigos,
auditoria, override por episódio, snapshot congelado, sem workspace). Pacote
`backend/app/continuity/` em **100%** de cobertura.

---

## Não-objetivos (declarados, não simulados)

- O resolver não altera o `GenerationSpec` nem injeta nada no Director,
  no Registry ou no Render — `ContinuityContext` é consumido explicitamente.
- Locks não versionam histórico próprio: a história vive nos snapshots de
  episódio; re-travar substitui (com `version` incrementada para auditoria).
- Location/Vehicle são travados por persona+campanha (uniforme e auditável);
  compartilhamento de set/veículo entre personagens é tema da V3.3 (Campaign
  Builder), não desta sprint.
