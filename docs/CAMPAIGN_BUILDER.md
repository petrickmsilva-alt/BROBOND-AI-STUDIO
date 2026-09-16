# Campaign Builder (V3.3)

Um briefing vira uma campanha completa: sete entregáveis, timeline de cinco
dias, deck de CTAs que nunca repete e um ZIP de exportação — sem pedir um
novo prompt.

O Director AI, o Provider Registry e o Render Engine não foram alterados: o
builder **planeja, agenda e empacota**. Um ativo só vira `delivered` quando
um arquivo real é anexado a ele — a campanha nunca afirma um render que não
existe.

---

## Modelo

Cinco tabelas (migração Alembic `0005`), sem foreign keys no banco — a mesma
convenção portátil SQLite/Postgres de personas (PR003), do grafo (V3.1) e da
continuidade (V3.2):

| Tabela | Conteúdo |
|---|---|
| `campaigns` | a raiz: produto, público, plataforma, objetivo, status e a `seed` do deck de CTAs |
| `campaign_briefs` | o briefing congelado: texto bruto + os seis campos + `missing`/`matched` |
| `campaign_episodes` | Dia 1..Dia 5: foco, CTA do dia e os kinds agendados, único por `(workspace, campaign, day)` |
| `campaign_assets` | um entregável por `(workspace, campaign, kind)`: formato, dia, prompt, CTA e chaves de entrega |
| `campaign_exports` | um ZIP do Export Center: object key, contagem de arquivos, sha256 e manifesto |

Todo acesso é **escopo de workspace**: id estrangeiro responde **404**, nunca
403. Criar a campanha grava raiz + brief + 7 ativos + 5 dias numa única
transação — a campanha nasce completa ou não nasce.

---

## O pipeline

```text
"Quero lançar a coleção Legacy"
        │
        ▼
brief_interpreter ──► InterpretedBrief (produto, público, plataforma, duração, objetivo)
        │
cta_engine ────────► deck determinístico (seed por campanha) ──► CTA principal
        │
timeline_builder ──► 7 AssetPlans (prompt por formato) + 5 EpisodePlans (Dia 1..Dia 5)
        │
campaign_repository ──► transação única: campaign + brief + assets + episodes
        │
export_center ─────► manifest.json + prompt.txt + metadata.json + MP4/PNG/thumb → ZIP
```

### Brief Interpreter

Framework-free, determinístico, português primeiro (com o vocabulário de
marketing em inglês aceito). Matching é insensível a acento e caixa. Cada
campo que o texto **não** carrega recebe o default documentado **e** entra
em `missing` — a UI mostra o que foi lido e o que foi inferido. O CTA nunca
é parseado do texto: é sorteado do deck.

### CTA Engine

O banco tem 28 templates ("Vista o extraordinário.", "{name} começa hoje.").
`deck_for(product, seed)` embaralha com `random.Random(seed)` — o mesmo par
reconstrói exatamente o mesmo deck — e a campanha sorteia da cursor: **nunca
repetir CTA** por construção (o deck valida unicidade em `__post_init__`).
Duplicar a campanha cunha uma seed nova: a cópia nunca repete as atribuições
da origem. O banco é livre de claims de escassez ("últimas peças") porque um
deck embaralhado pode pôr qualquer CTA no Dia 1.

### Multi deliverables + Timeline

Os sete formatos nascem do briefing, cada um com cena, prompt e CTA:

| Dia | Foco | Entregáveis |
|---|---|---|
| 1 | Lançamento | Reel 9:16 (MP4) + Thumbnail (PNG 16:9) |
| 2 | Bastidores | Story (PNG 9:16) |
| 3 | Alcance | Shorts (MP4) + YouTube Cover (PNG 2560×1440) |
| 4 | Conversão | Feed 1:1 (PNG 1080×1080) |
| 5 | Última chamada | Banner (PNG 1200×628) |

Cada dia tem foco, CTA e conjunto de ativos **diferentes** — verificado por
teste. O prompt composto (produto + cena + público + plataforma + duração +
CTA do ativo) passa pelo `PromptEnhancer` existente — a fachada do
`PromptCompiler` do Core. Nada de string solta.

### Export Center

O ZIP contém `manifest.json` (campanha + brief + timeline + ativos), e por
ativo `{dia:02d}-{kind}/prompt.txt` + `metadata.json`. Ativos **entregues**
contribuem o binário real — `delivery.mp4` (vídeo), `delivery.png` (imagem),
`thumbnail.png` quando anexado — lido do storage. Ativo sem arquivo real
contribui só texto: **nada é inventado**. O ZIP é gravado via adaptador de
storage e servido pela rota autenticada `/api/v1/assets/download/{key}`.

---

## Rotas (todas com identidade)

| Método | Rota | Faz |
|---|---|---|
| `POST` | `/api/v1/campaigns/interpret` | lê o briefing sem persistir (preview) |
| `POST` | `/api/v1/campaigns` | constrói a campanha completa (201) |
| `GET` | `/api/v1/campaigns` | lista as campanhas do workspace |
| `GET` | `/api/v1/campaigns/{id}` | detalhe: brief + 7 ativos + 5 dias + exports |
| `POST` | `/api/v1/campaigns/{id}/duplicate` | copia com CTAs re-armados e entregas zeradas |
| `POST` | `/api/v1/campaigns/{id}/assets/{asset_id}/deliver` | anexa arquivo real (planned → delivered) |
| `POST` | `/api/v1/campaigns/{id}/export` | constrói o ZIP e registra o export |

Cada mutação escreve no audit log (`campaign.created`, `campaign.duplicated`,
`campaign.asset.delivered`, `campaign.exported`). Entrega valida que a chave
é do workspace do chamador **e** existe no storage (422 caso contrário).

---

## Camadas

Mesma regra de `continuity/`: `brief_interpreter`, `cta_engine`,
`timeline_builder` e `export_center` são framework-free (stdlib apenas) e
razoam sobre dados planos; `campaign_models` tem as tabelas SQLAlchemy;
`campaign_repository` é o único módulo que toca o banco;
`campaign_service` compõe o fluxo no limite da aplicação. Cobertura do
pacote: **100%**.

UI: `/studio/campaigns` — `BriefPanel`, `CampaignCalendar`,
`CampaignAssets` e `ExportPanel`; a lista de campanhas, duplicar e exportar
ficam na página. O download do ZIP usa a rota autenticada de assets.
