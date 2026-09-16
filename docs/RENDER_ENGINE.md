# PR008 — Cinematic Render Engine

PR008 conecta o Director AI ao Generation Executor para produzir imagens e
vídeos reais. É o PR que ativa a renderização: até aqui, o Director
planejava (PR005), o storyboard editava o plano (PR006) e os Providers
executavam specs avulsas (PR007) — mas nenhum storyboard era renderizado.

---

## Fluxo

```text
ProductionPlan (PR005) ou StoryboardState (PR006)
  -> SceneRenderer + PromptCompiler -> GenerationSpec (uma por cena)
  -> GenerationExecutor -> Registry -> Provider (PR007)
  -> ProviderAsset -> RenderAssetPipeline -> PNG/MP4 + thumbnail + metadata
  -> ProviderJob registrado por cena
```

O orquestrador nunca chama um Provider diretamente: a única dependência
voltada a providers é o `GenerationExecutor`, que resolve adapters pelo
registry. Ids de provider trafegam como strings opacas no lote e no spec.

---

## Entidade central

`RenderBatch` é o lote de render, com cenas de progresso independente:

```text
batch_id
workspace_id
project_id
kind                image | video
provider            id opaco ("" = padrão do kind)
scenes[]            RenderScene, cada uma com status e progress 0-100
status              queued | running | rendering | completed | failed | cancelled
eta_seconds         estimativa a partir das cenas já medidas
```

`running` significa que o orquestrador aceitou o lote; `rendering` significa
que a primeira cena chegou ao executor. A distinção importa para a Fila: um
lote pode estar aceito antes de qualquer trabalho de GPU começar.

No backend, a entidade vive em:

```text
backend/app/render/render_batch.py
```

---

## Scene Renderer

Cada cena gera um `GenerationSpec` com os campos obrigatórios:

```text
persona, style, mood, camera, lens, lighting, motion,
seed, aspect_ratio, duration
```

O texto do prompt é produzido somente pelo `PromptCompiler` existente: o
renderer monta `PromptBlocks` e compila, como o Director faz no
planejamento. `mood` não tem bloco próprio, então viaja em COLOR (o grade
que o mood implica) e CONTINUITY (o mood precisa se sustentar na sequência).

Fontes de entrada, em ordem de produto:

1. `StoryboardScene` (PR006) — o plano editado, com mood por cena;
2. `ShotPlan` (PR005) — o plano do Director, sem edição;
3. dicionários — o payload da API, que carrega o plano inline porque planos
   de produção não são persistidos no servidor.

Seeds são determinísticas por desenho: cenas sem seed própria recebem
`base + índice`, então recriar o mesmo lote renderiza as mesmas seeds.

```text
backend/app/render/scene_renderer.py
```

---

## Progress Engine

WebSocket push, sem polling:

```text
/ws/render/{batch_id}
```

Eventos, em ordem de ciclo de vida:

```text
batch_started -> scene_started -> scene_progress -> scene_completed
             ... por cena ... -> batch_completed
```

Falhas e cancelamentos viajam no payload (`status`/`error` em
`scene_completed`/`batch_completed`), não em nomes extras de evento: o
cliente trata exatamente cinco tipos de evento.

O cliente não envia nada: recebe um `snapshot` com o lote completo,
repassa o histórico em buffer e aguarda eventos ao vivo até o
`batch_completed` terminal. O hub é thread-safe — publicações de outra
thread acordam o loop assinante em vez de tocar a fila diretamente.

```text
backend/app/render/progress.py
```

---

## Asset Pipeline

Por cena, o pipeline salva automaticamente pelo `StorageService` existente
(o AssetStore — nenhum backend novo de storage):

```text
arquivo principal   PNG (imagem) ou MP4 (vídeo)
thumbnail           PNG redimensionado (imagem) ou cópia jogável (vídeo)
metadata            JSON com prompt, seed e provider
```

`prompt`, `seed` e `provider` vão no JSON de metadados e são ecoados no
`RenderAsset`, então a Fila e a biblioteca mostram o que produziu cada cena
sem abrir o arquivo. Quando há sessão de banco, uma linha `Asset` por
arquivo é criada e o render aparece em `GET /api/v1/assets`.

Thumbnails de vídeo são uma cópia dos bytes do MP4: extrair um frame exige
um estágio ffmpeg que ainda não existe, e uma cópia jogável é um preview
honesto — os bytes são o render. Thumbnails de imagem usam Pillow quando
importável e caem para cópia de bytes sem ele.

```text
backend/app/render/asset_pipeline.py
```

---

## API

Seis rotas sob `/api/v1/render`, todas com `Depends(current_user)` — renders
persistem no workspace de quem chamou:

| Método | Rota | Efeito |
| --- | --- | --- |
| `POST` | `/api/v1/render/batches` | Cria o lote a partir do storyboard inline (201, nada renderiza) |
| `GET` | `/api/v1/render/batches` | Fila do chamante, mais novos primeiro |
| `GET` | `/api/v1/render/batches/{batch_id}` | Lote com progresso por cena |
| `POST` | `/api/v1/render/batches/{batch_id}/start` | Renderiza em background (202 = aceito, não pronto) |
| `POST` | `/api/v1/render/batches/{batch_id}/cancel` | Cancela (idempotente) |
| `POST` | `/api/v1/render/batches/{batch_id}/retry` | Repete só falhas/canceladas de um lote terminado |

Regras de tenant: lote inexistente ou de outro workspace responde 404, como
jobs e assets. `start` em lote não-`queued` responde 409; `retry` em lote
ativo ou sem nada a repetir responde 409. Uma cena que falha não para as
irmãs — o lote termina `failed` e o retry só repete as falhas. Cancelar é
cooperativo: a cena em execução termina, as demais vão para `cancelled`.

---

## Frontend

Nova tela `/studio/render`:

- Storyboard (brief → plano do Director, inline);
- Progresso geral, cena atual e tempo estimado (ETA);
- Preview por cena (imagem ou vídeo) com Download;
- Fila: na fila, executando, concluído, falhou — com Cancelar e Repetir.

O progresso chega por WebSocket (`wsUrl('/ws/render/{id}')`); a lista só é
recarregada por ação do usuário ou evento de socket — sem polling.

---

## Limites declarados

- Lotes vivem em memória (`RenderBatchStore`): um restart derruba lotes na
  fila. Os artefatos duráveis são as linhas `Asset` que o pipeline escreve.
- O hub de progresso é in-process, como o da fila (ETAPA 11): com múltiplas
  instâncias da API, o socket precisa alcançar a instância que renderiza.
- Uma cena por vez, em ordem: paralelismo por cena é evolução futura.
- Thumbnails de vídeo são cópias jogáveis até existir extração de frames.

---

## Testes

`backend/tests/test_pr008_render_engine.py` cobre RenderBatch,
SceneRenderer, Executor (via orquestrador), WebSocket de progresso, assets
e frontend estrutural. O pacote `backend/app/render` está em 100%.
