# Cinematic Asset Studio (V4.0.1 · PR013)

A aba **Assets** deixa de ser um placeholder e vira a biblioteca profissional
do studio: upload funcional com progresso real, grade responsiva com a
ficha completa de cada asset, preview de imagem e vídeo, filtros com busca
instantânea e estados vazios cinematográficos — tudo sobre o Design System
existente, sem tocar em Provider Registry, Render Engine, Director AI,
Prompt Compiler ou GenerationExecutor.

A regra de honestidade que organiza o módulo inteiro: **um campo
desconhecido renderiza `—`, nunca um zero, uma unidade inventada ou um
label chutado.** O backend espelha isso (`NULL` no banco significa
"desconhecido"); o frontend aprende-o em `UNKNOWN_LABEL = '—'`.

---

## Os três endpoints (ETAPA 2)

| Método | Caminho | Função |
|---|---|---|
| `GET` | `/api/v1/assets/library` | Lista a biblioteca do workspace; filtros server-side `kind`, `project`, `persona`, `provider`, `min_score`, `date_from`, `date_to`, `q` |
| `POST` | `/api/v1/assets/library/upload` | Ingest **multipart/form-data** com `UploadFile` — nunca arquivo como JSON |
| `GET` | `/api/v1/assets/library/{asset_id}` | Detalhe de um asset (mesmo payload enriquecido da lista) |

Todas exigem Bearer (workspace por token). O isolamento por tenant usa a
mesma convenção de alias do Storage: `{directory}` pode chegar como
`{workspace}` na URL pública, mas o nome de arquivo e o SHA-256 nunca batem
entre usuários diferentes — verificado por teste cross-tenant.

Aceitos no upload (e só eles): **PNG, JPG, WEBP, MP4, MOV**. Qualquer
outro `Content-Type` responde **415**, sem efeito colateral. Cada ingest
persiste: bytes via `StorageService` existente (disco local/S3), linha
`Asset`, `AssetMetadata` (MIME, tamanho, SHA-256, resolução, dimensões,
duração, seed, provider, project, persona, tags, quality) e, quando a
imagem permite, o `Thumbnail` derivado (Pillow; vídeo sem poster quando
ffmpeg não está disponível — um ícone honesto renderiza no lugar, nunca um
frame fabricado). Cada upload registra `asset.uploaded` no audit log.

`before_asset_id` no formulário vincula comparações: o campo `before_url`
do payload alimenta o slider **Before / After** do preview — real quando a
ligação existe, ausente quando não existe.

## O pipeline do service (ETAPA 2)

`library_service.py` faz, em ordem, e nada mais:

1. **cheiro do arquivo** — o `Content-Type` declarado passa pelo
   accept-list antes de qualquer byte ser gravado (415 cedo);
2. **bytes em disco** — `StorageService` existente (nenhum caminho novo de
   I/O nasceu neste sprint);
3. **fatos medidos** — SHA-256, tamanho e, para imagens, dimensões via
   Pillow; duração/dimensões de vídeo ficam `NULL` sem probe (honesto);
4. **linha + metadados** — `Asset` + `AssetMetadata` na mesma transação,
   tags normalizadas;
5. **thumbnail** — derivado real gravado pelo mesmo storage; falhas de
   Pillow viram `thumbnail_url = NULL`, nunca exceção 500;
6. **audit** — `asset.uploaded` com workspace e nome do arquivo.

`GET /assets/library` lê essas linhas e responde
`AssetLibraryEntryResponse` com `has_metadata: false` para as linhas
legadas anteriores ao V4.0.1 — o frontend desenha essas com tile em vez de
thumbnail.

## O frontend (ETAPAS 1, 3–6)

Camadas, na disciplina de boundary que o repo inteiro segue:

| Camada | Onde | O que faz |
|---|---|---|
| Rede | `lib/network/upload.ts` | **Único** XHR do app (`fetch` não reporta progresso de upload): percent real, bytes/s suavizados, `x-brobond-trace`, erros tipados no mesmo `NetworkErrorType`, sem retry silencioso |
| API | `lib/api.ts` | `listAssetLibrary`, `getLibraryAsset`, `uploadLibraryAsset`, `libraryQuery` — delegam; `lib/api.ts` continua sem `fetch(` |
| Domínio puro | `lib/assets/library.ts` | accept-list, máquina de fila, filtros instantâneos, formatadores, bandas de score (as mesmas bandas do Quality Engine: `<70` retry, `70–84` review, `85–94` approved, `≥95` masterpiece) |
| Componentes | `app/components/studio/assets/` | `AssetDropZone` (área inteira + contador de profundidade contra flicker), `UploadQueueList` (percent, velocidade, tamanho e os 4 estados), `AssetGrid` (10 fatos por card), `AssetFilterBar`, `AssetPreviewDialog` (lightbox, zoom discreto, Before/After, player com timeline/loop/download), `AssetEmptyState` (5 estados), `AssetLibraryClient` (orquestrador) |
| Conta-gotas | `app/page.tsx` | só o chrome da página; recebe `{all, image, video}` **contados** do orquestrador |

Fluxo de leitura: `listAssetLibrary()` uma vez por montagem/retry; filtros
e busca re-aplicam **instantaneamente em memória** sobre a lista completa
(os parâmetros server-side existem para consumidores da API). Fluxo de
ingest: drop/pick → fila sequencial (um upload por vez — justo com o
medidor de velocidade) → item a item por `uploadLibraryAsset` → sucesso
move o asset para a frente da grade e soma nos contadores.

Estados vazios (ETAPA 6): biblioteca vazia, upload em curso, erro (com o
texto exato da resposta), sem conexão (o mapeamento `OFFLINE`/`CORS`/
`TIMEOUT` da V3.2.1 — nunca "a API caiu") e "filtros zeraram tudo".

## Estilos

Novas classes prefixadas `al-*` (apêndice ao final de `app/globals.css`),
usando as variáveis legadas do shell (`--purple`, `--line`, `--panel`) mais
os tokens `--bb-*` quando a superfície é nova. Nenhuma classe existente foi
tocada (`.empty-library`, `.asset-grid`, `.asset-item` seguem servindo os
outros módulos).

## Cobertura e guards

- Módulo `backend/app/assets`: **100%** statements e branches
  (`backend/tests/test_asset_library.py`, 52 testes — multipart real contra
  SQLite em memória, Pillow real, falha de ffmpeg simulada, isolamento
  cross-tenant, rotas sem workspace).
- Frontend: `lib/assets/library.ts` em **100%**; componentes em
  98.4 %–100 % por arquivo; os novos arquivos entram no piso global de 98 %
  do `vitest.config.ts` (296 testes no total).
- Os guards de inventário acompanham o crescimento legítimo: 114 rotas
  `/api/v1` (era 111), snapshot `73 required / 3 optional / 38 public`,
  `docs/ETAPAS.md` P0-4 atualizado — comentários datados nos próprios
  testes, como sempre.
