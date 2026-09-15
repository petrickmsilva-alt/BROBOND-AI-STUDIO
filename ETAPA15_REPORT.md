# ETAPA 15 — UX PREMIUM

Relatório técnico. Escopo: a superfície do produto — o que o usuário vê e o que ela afirma.

**Resultado:** o Diretor virou a porta de entrada, as rotas Core ficaram alcançáveis, a casca
parou de inventar fatos e o resultado mostrado passou a ser o render de verdade.
`850 → 881` testes. Zero arquivos deletados. Backend intocado: **58 rotas, 31 core, 2 WS** —
os mesmos números da ETAPA 14.

---

## 1. Auditoria — tudo medido antes de escrever

O frontend inteiro são 5 arquivos: `app/page.tsx`, `components/studio-shell.tsx`, `lib/api.ts`,
`app/layout.tsx`, `app/globals.css`.

| # | Achado | Como foi medido |
| --- | --- | --- |
| H1 | **Zero rotas Core consumidas** | `grep -rn "api/v1/core" app components lib` → nenhuma ocorrência |
| H2 | A casca inventa GPU, saudação, contagens e versão de LoRA | `grep -o` por cada string fabricada: todas presentes |
| H3 | **O resultado mostrado não é o render** | `grep -c "output_url" app/page.tsx` → **0**; a tela desenha `result-person` e rotula `FLUX / 2K` |
| H4 | Todo erro vira "offline" | `lib/api.ts`: `if (!response.ok) throw` dentro de `try` cujo `catch` devolve `{data: null, remote: false}` |
| H5 | Os controles não comandam a requisição | `createImageJob({ ..., aspect_ratio: '16:9', ... })` literal, com `<select>` de 9:16 ao lado |
| H6 | Origem fixa no browser | `API_URL` default `http://localhost:8000` |
| H7 | Timeout de 2,2 s para tudo | `AbortSignal.timeout(2200)` |
| H8 | Módulo "Motion control" 100% estático | nenhuma chamada de API em toda a função |

### H1 — catorze etapas inalcançáveis do produto

A API expõe **31** rotas `/api/v1/core/*`. A interface usava 8 rotas legadas:
`/prompts/enhance`, `/generations/{images,videos}`, `/jobs/*/cancel`, `/personas`,
`/storyboards/expand`, `/assets`, `/auth/*`.

O ponto mais grave: `SYSTEM_PROMPT.md` diz que "o usuário conversa com um diretor de cinema,
não com um campo de prompt". A tela principal **era** um campo de prompt com um botão
"Enhance". O `/api/v1/core/direct` da ETAPA 7 — que devolve conceito, roteiro, beats, música,
ritmo, duração e uma pergunta de direção — nunca era chamado.

### H3 — a mentira mais cara

```
grep -c "output_url" app/page.tsx  ->  0
```

`output_url` estava no tipo `Job`, era recebido pelo WebSocket, e nunca era lido. No lugar, a
tela renderizava uma figura CSS (`result-person` com `head` e `body`) rotulada **"FLUX / 2K"**.
Um job `failed`, um `cancelled` e um `complete` mostravam **a mesma imagem**.

Isso é a violação de `SYSTEM_PROMPT.md` na sua forma mais direta: "Não invente arquivos, jobs
concluídos, modelos carregados ou outputs inexistentes."

### H2 — o que a casca afirmava sem saber

| Afirmava | O que a API responde de verdade |
| --- | --- |
| `GPU ready · RTX 4090 · 18.4 / 24 GB VRAM` | `{"available": false, "backend": "cpu", "message": "nvidia-smi not found"}` |
| `Good evening, Petrick` | nada — hora e usuário não eram consultados |
| `128 / 84 / 24 / 2 / 18` assets | `/api/v1/assets` devolve a lista real |
| `72 / 2,000` | o campo tinha outro comprimento |
| `LoRA v1.2` | nenhum treino tinha ocorrido |

---

## 2. O que foi feito

### 2.1 O Diretor como porta de entrada

`DirectorStudio` é o módulo padrão (`useState('director')`). Consome `/api/v1/core/direct` e
mostra: formato, conceito, logline, roteiro, música, ritmo, linguagem de câmera e luz,
duração, e os beats com objetivo, câmera, luz, emoção e duração.

Quando `brief.clarification` vem preenchida — intenção ambígua ou empate entre formatos, o que
a ETAPA 7 passou a detectar — a pergunta aparece em destaque, porque o diretor pediu uma
resposta e engoli-la seria decidir por ele.

### 2.2 Proxy relativo

```js
{ source: '/api/v1/:path*', destination: `${backend}/api/v1/:path*` }
```

`API_URL` passa a ser `''` e o alvo é `BROBOND_API_PROXY_TARGET`. O browser não recebe mais
uma origem que pode não alcançar. `wsUrl()` deriva o socket de `window.location.origin`.

Verificado por handshake, não por suposição:

```
direto na API (8000):  HTTP/1.1 101 Switching Protocols
via proxy Next (3000): HTTP/1.1 101 Switching Protocols
```

### 2.3 Contrato de erro honesto

```ts
type ApiResult<T> = { data: T; remote: boolean; status?: number; error?: string }
```

`remote` continua significando "chegou dado utilizável" — nenhum chamador antigo quebrou.
`status` e `error` separam o que antes era um caso só:

- **sem resposta** → `error: 'offline'`
- **o servidor respondeu com erro** → `status: 401|422|500` e o `detail` do FastAPI extraído

O login agora distingue: `if (result.status)` mostra a rejeição real; só a ausência de
resposta oferece a sessão local.

### 2.4 O resultado real

```tsx
{job?.output_url ? <img className="result-image" src={job.output_url} alt={prompt} />
                 : <div className="result-pending">…</div>}
```

Com mensagens distintas para `failed` ("The render failed — no image was produced"),
`cancelled` e "ainda renderizando". A figura CSS saiu do caminho do resultado.

### 2.5 Os controles comandam

`model`, `aspect_ratio` e `resolution` saíram do payload literal e viraram estado ligado aos
`<select>`, com as opções carregadas de `/api/v1/models/{image,video}`. O mesmo no vídeo
(`duration`, `aspect`, toggles de áudio nativo e modo cinematográfico).

### 2.6 Storyboard pelo Core

Passou de `/storyboards/expand` para `/api/v1/core/storyboard`, então mostra os shots
realmente escalados (código, família, lente, duração) **e** as violações e atenções que o
motor reporta — em vez de quatro títulos genéricos.

### 2.7 Motion control removido da navegação

Era inteiramente estático: nenhuma chamada, nenhum estado. Mantê-lo ao lado de painéis que
funcionam ensinava o usuário a desconfiar dos que funcionam. A remoção é de navegação; nenhum
arquivo foi apagado.

---

## 3. Um erro meu nos testes

`test_the_gpu_card_reads_the_api` proibia a string `/api/v1/system/gpu` em `page.tsx`,
assumindo que só poderia ser uma chamada. Ela aparece num **rótulo para o usuário** —
`querying /api/v1/system/gpu` — que é justamente o comportamento honesto que eu queria.
Reescrito para proibir `fetch(` em `page.tsx`, que é a regra real.

---

## 4. Não-vacuidade

| Defeito reintroduzido | Resultado |
| --- | --- |
| `<strong>RTX 4090</strong>` no lugar do dado real | **1 failed** — `test_the_shell_does_not_invent_facts[RTX 4090]` |
| `API_URL ?? 'http://localhost:8000'` | **1 failed** — `test_the_client_does_not_default_to_localhost` |

Restaurado: **881 passed**.

---

## 5. Verificações literais

| Verificação | Antes | **Depois** |
| --- | --- | --- |
| `pytest backend/tests -q` | 850 | **881 passed** |
| 22 testes originais · independência | 22 · 23 | **22 · 23** |
| Rotas `/api/v1` · core · WS | 58 · 31 · 2 | **58 · 31 · 2** (inalterado) |
| Rotas Core no cliente | 0 | **6** |
| `npm run build` (com checagem de tipos) | ✓ | **✓** |
| Arquivos deletados desde `3708784` | 0 | **0** |

Executado de verdade, não só compilado:

```
pagina            HTTP 200
/api/v1/health          -> 200 (via proxy)
/api/v1/system/gpu      -> 200 (via proxy)
/api/v1/system/readiness-> 200 (via proxy)
/api/v1/core/quality/rules -> 200 (via proxy)
POST /api/v1/core/direct   -> brief real em PT ("Comercial de produto com valor
                              percebido construído por luz e escala")
POST /api/v1/core/direct {}-> 422 atravessa o proxy
WebSocket via proxy        -> 101 Switching Protocols
```

E na página servida, as fabricações conferidas uma a uma: `RTX 4090`, `18.4 / 24 GB`,
`Good evening, Petrick`, `LoRA v1.2`, `12 renders`, `FLUX / 2K`, `result-person` — **todas
ausentes**.

`backend/tests/test_frontend_honesty.py`: **31 guardas** estruturais, no estilo que o
repositório já usa para o próprio fonte.

---

## 6. O que **não** foi feito, dito explicitamente

- **Quatro rotas Core estão no cliente mas ainda sem painel.** `direct` e `storyboard` têm
  interface; `timeline`, `quality/assess`, `quality/rules` e `providers` estão tipadas e
  chamáveis em `lib/api.ts`, mas nenhuma tela as mostra. É trabalho restante, não entregue.
- **`components/studio-shell.tsx` (644 linhas) não foi tocado.** Não está montado em
  `app/layout.tsx` — a página renderiza `app/page.tsx`. Mantive-o intacto em vez de
  reescrever um componente que o produto não usa; decidir o destino dele é do mantenedor.
- **Nenhum teste JavaScript foi adicionado.** O repositório não tem runner de front
  (sem jest/vitest), e instalá-lo é escopo da ETAPA 16 (Testes 90%). As 31 guardas rodam no
  pytest lendo o fonte — cobrem presença e ausência, não comportamento em runtime.
- **O resultado real não foi visto renderizado.** Não há GPU nem `diffusers`/`torch`, então
  nenhum job produziu `output_url` de verdade nesta máquina. O caminho `<img src={job.output_url}>`
  foi verificado por guarda estrutural e pelo contrato do WebSocket, não por uma imagem na tela.
- **A vulnerabilidade do `next@14.2.32` permanece.** Sinalizada pelo npm durante a instalação;
  atualizar o framework é decisão do mantenedor, não desta etapa.

---

## 7. Arquivos

| Arquivo | Mudança |
| --- | --- |
| `app/page.tsx` | reescrito — 459 l. Diretor, GPU/readiness reais, resultado real, controles ligados, `Notice` em cada painel |
| `lib/api.ts` | reescrito — 334 l. Contrato de erro, `wsUrl`, rotas de sistema e 6 rotas Core tipadas |
| `next.config.mjs` | rewrite `/api/v1` com alvo por env |
| `app/globals.css` | +60 linhas para Diretor, avisos, readiness e resultado |
| `backend/tests/test_frontend_honesty.py` | **novo** — 31 guardas, 222 l |
| `CHANGELOG.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `README.md`, `backend/README.md` | atualizados |

Nenhum arquivo deletado. **Nenhum arquivo de backend foi alterado nesta etapa** — as 58 rotas,
o `QualityGate`, o `VideoTimeline`, o `DirectorAgent` e os providers estão exatamente como a
ETAPA 14 os deixou, o que os 881 testes confirmam.
