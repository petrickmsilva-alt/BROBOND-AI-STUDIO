# PR011 — GPU Cluster (RunPod) e conectores Flux/Wan

PR011 liga o Provider Registry a GPUs externas. Nada além da camada de
providers foi tocado: Director AI, Storyboard Engine, Prompt Compiler e a
superfície pública do Provider Registry continuam byte a byte como estavam.

O que existe de novo são **cinco arquivos** em `backend/app/providers/` e uma
linha em `app/main.py` que compõe o bloco `gpu` do readiness.

```text
backend/app/providers/
├── gpu_client.py             transporte: HTTP async, retry, poll, cancel, upload/download
├── runpod_base.py            ciclo de vida compartilhado: spec -> payload -> job -> bytes -> asset
├── runpod_flux_provider.py   imagem: image, upscale, inpaint, outpaint, control reference
├── runpod_wan_provider.py    vídeo: text-to-video, image-to-video, duração, fps, seed, câmera
└── gpu_health.py             o bloco `gpu` de GET /api/v1/system/readiness
```

---

## 1. A divisão de responsabilidade

A regra que organiza o PR inteiro: **o client não sabe o que é um
`GenerationSpec`; o conector não sabe o que é um status HTTP.**

| Camada | Sabe | Não sabe |
| --- | --- | --- |
| `gpu_client.py` | URL, header, status code, backoff, base64, deadline | prompt, seed, aspect ratio, modelo |
| `runpod_*_provider.py` | spec, modo, câmera, duração, envelope do job | retry, header, polling, download |
| `generation_executor.py` (PR009, intocado) | `BaseProvider` | que existe um cluster |

Por isso `test_runpod_flux.py` e `test_runpod_wan.py` têm uma asserção de
código-fonte que falha se as strings `Authorization`, `status_code`, `httpx`
ou `await` aparecerem num conector. Não é estilo: é a fronteira que mantém os
dois arquivos legíveis.

---

## 2. GPU Client (ETAPA 1)

`GpuClient` é async, configurável e sem regra de negócio.

| Responsabilidade | Como |
| --- | --- |
| HTTP async | `GpuTransport`, um `Protocol`. O default (`HttpxTransport`) importa `httpx` **dentro** da chamada, então o módulo é importável em qualquer máquina. |
| Timeout configurável | por client (`BROBOND_GPU_TIMEOUT`) e por chamada. `0` desliga o prazo. |
| Retry exponencial | 3 tentativas, backoff `0.5s → 1s → 2s`, cap em `8s`. |
| Poll de jobs | `poll()` percorre `IN_QUEUE → IN_PROGRESS → terminal` no intervalo `BROBOND_GPU_POLL_INTERVAL`. |
| Cancelamento | `cancel(job_id)`; nunca levanta exceção. |
| Upload de referência | `upload_reference()` → data URI base64. |
| Download do resultado | `download()` aceita URL, data URI ou base64 puro. |

### O que é e o que não é retryable

Um 4xx **não** é repetido. Um payload malformado vai falhar de forma idêntica
três vezes, só que mais devagar, e ainda por cima gastando o deadline que
protegeria uma falha de verdade. Repetidos: `408, 425, 429, 500, 502, 503,
504` e falhas de transporte (DNS/TCP/TLS).

### Timeout cancela o job

Quando o deadline estoura, o client **manda cancelar antes de desistir**:

```python
if deadline > 0 and elapsed + interval > deadline:
    await self.cancel(job_id)
    raise GpuTimeout(...)
```

Abandonar um job de GPU sem cancelar não é uma render perdida, é uma fatura.

### Segredo

A chave viaja só no header `Authorization` e não aparece em retorno, log,
mensagem de erro ou health. Duas consequências deliberadas:

- `_safe_url()` reduz qualquer URL a `scheme://host` antes de entrar numa
  mensagem de erro — mensagens deste módulo chegam ao `/system/readiness`, que
  é público, e o *path* de um endpoint serverless carrega o id do endpoint;
- ao baixar de uma URL de resultado (pré-assinada, host de terceiro) o client
  **não** envia o header de autorização.

### Ponte síncrona

`BaseProvider` é síncrono desde PR007 e vinte módulos dependem disso.
`run_sync()` faz a ponte: normalmente `asyncio.run`, e — quando já existe um
loop rodando na thread — numa thread própria, porque `asyncio.run` não aninha.
Nenhum `async def` vazou para o contrato de provider.

---

## 3. RunPod Flux (ETAPA 2)

`provider_id: runpod-flux` · modelo default `flux-kontext-pro` · VRAM `24GB`

| Operação | `spec.mode` | Precisa de referência |
| --- | --- | --- |
| image | `text-to-image` | não |
| image-to-image | `image-to-image` | sim |
| inpaint | `inpaint` | sim |
| outpaint | `outpaint` | sim |
| control reference | `control` | sim |
| upscale | *(método)* | o asset de origem |

### Por que as operações não viraram campos de `ProviderCapabilities`

`ProviderCapabilities` é o contrato público congelado em
`docs/API_SNAPSHOT.json` e devolvido por `GET /api/v1/providers`; a regra
absoluta do PR011 proíbe alterar a superfície pública do Provider Registry.
Então as cinco operações são declaradas no conector, em
`SUPPORTED_OPERATIONS` + `supports_operation()`, e o registro público mantém
seus 8 campos (`supports_image=True`, `supports_upscale=True`). Nada fica
escondido: o conjunto é testado e está documentado aqui.

O conector recebe **apenas** `GenerationSpec` — verificado por assinatura, não
por convenção:

```python
list(inspect.signature(RunPodFluxProvider.generate_image).parameters)
# ['self', 'spec', 'output_dir']
```

Uma operação de referência sem `spec.reference_path` levanta `ValueError`
**antes** de gastar um segundo de GPU. É fatal de propósito: o retry engine
(PR009) não repete `ValueError`, e repetir não faria aparecer a imagem que
não existe.

---

## 4. RunPod Wan (ETAPA 3)

`provider_id: runpod-wan` · modelo default `wan-2.1-t2v-14b` · VRAM `48GB`

| Operação | `spec.mode` | Precisa de referência |
| --- | --- | --- |
| text-to-video | `text-to-video` | não |
| image-to-video | `image-to-video` | sim (primeiro frame) |

Controles honrados: `duration`, `fps`, `seed` e **camera motion**.

### Camera motion sem tocar o Storyboard

A regra da etapa é explícita: *nunca acessar Storyboard diretamente*. E não é
preciso. Quando um spec chega aqui, a intenção de câmera já passou por três
camadas e virou dois campos tipados:

```text
StoryboardEngine (plano)
  -> DirectorAgent (interpretação)
     -> PromptCompiler (prompt_compiled)
        -> GenerationSpec.motion + .motion_strength
           -> RunPodWanProvider  (lê só estes dois campos)
```

`CAMERA_MOTIONS` é uma **tabela de tradução** do vocabulário que o spec já
carrega (`"slow push in"`) para o token que este worker espera (`"push_in"`) —
exatamente o papel de `PIPELINE_CLASS_BY_MODE` no conector local. Não é uma
segunda fonte de verdade sobre cinematografia: um movimento desconhecido
**passa adiante intacto** em vez de ser descartado, para que um movimento novo
do Director chegue ao cluster antes de esta tabela aprender sobre ele.

`test_runpod_wan.py` falha se `storyboard`, `director`, `SceneBeat` ou
`ShotPlan` aparecerem no arquivo.

### Clamp de duração e fps

O endpoint aceita 1–10s e 8–30fps. Um spec fora disso é **limitado, não
recusado**, e o clamp fica registrado no metadata do asset
(`"clamped": true`). Matar um batch inteiro porque uma cena pediu 30 segundos
seria pior do que renderizar o clipe mais longo possível e dizer que foi
cortado.

---

## 5. Execução de job (ETAPA 4)

```text
GenerationSpec
  -> GenerationExecutor          (PR009, intocado)
     -> RetryEngine -> TimeoutManager
        -> RunPodFluxProvider / RunPodWanProvider
           -> GpuClient.submit()   POST /run      -> job_id
           -> GpuClient.poll()     GET  /status/{id}   (backend)
           -> GpuClient.download() bytes -> arquivo
  -> ProviderAsset -> ProviderJob -> Quality Engine
```

O Render Engine continua chamando apenas
`GenerationExecutor.execute(spec, output_dir, ...)`. Ele não sabe que existe um
cluster, e é por isso que ligar o RunPod não exigiu uma linha em
`backend/app/render/`.

**Nenhum polling no frontend.** O browser não conhece `job_id` de RunPod, nem
`/status/`, nem o host do cluster; progresso continua chegando pelo WebSocket
`/ws/render/{batch_id}`. Há um teste que lê `app/`, `lib/` e `components/` e
falha se as strings `runpod`, `/status/` ou `RUNPOD` aparecerem.

### Tradução de falhas

Toda falha de GPU vira `ProviderUnavailable`, que é precisamente o que a
pilha de resiliência do PR009 já sabe repetir e contornar:

| Situação | Resultado |
| --- | --- |
| cluster sem credencial | `ProviderUnavailable` nomeando as duas variáveis |
| job `FAILED`/`CANCELLED`/`TIMED_OUT` | `ProviderUnavailable` com o erro do worker |
| deadline estourado | job cancelado + `ProviderUnavailable` |
| 5xx persistente | `ProviderUnavailable` após 3 tentativas |
| job completo sem artefato | `ProviderUnavailable` — sucesso vazio é mentira, não sucesso |
| referência ausente | `ValueError` **fatal** (não repetido) |

Com o fallback do PR009 ligado, o batch termina no `MockProvider` com o motivo
registrado no Job em vez de morrer.

---

## 6. Configuração (ETAPA 5)

Quatro variáveis, **todas opcionais em DEV**:

| Variável | Default | Significado |
| --- | --- | --- |
| `BROBOND_RUNPOD_API_KEY` | *(vazio)* | credencial; só o backend a vê |
| `BROBOND_RUNPOD_ENDPOINT` | *(vazio)* | ex. `https://api.runpod.ai/v2/<endpoint-id>` |
| `BROBOND_GPU_TIMEOUT` | `300` | segundos por job (`0` desliga o prazo) |
| `BROBOND_GPU_POLL_INTERVAL` | `2` | segundos entre polls |

Sem elas o app sobe igual, o readiness responde `200` com
`gpu.available: false` e a razão, e toda a suíte roda num laptop sem conta na
RunPod. As duas primeiras são exigidas **juntas**: endpoint sem chave toma
401, chave sem endpoint não tem para onde ir.

No `render.yaml` elas entram como `sync: false` — a Render pede o valor no
deploy e ele não fica no arquivo nem no git.

---

## 7. Health (ETAPA 6)

`GET /api/v1/system/readiness` ganha o bloco `gpu`:

```json
{
  "gpu": {
    "available": true,
    "provider": "runpod",
    "model": "flux-kontext-pro",
    "vram": "24GB",
    "latency_ms": 380
  }
}
```

Indisponível, com as **mesmas chaves** e uma razão legível:

```json
{
  "gpu": {
    "available": false,
    "provider": "runpod",
    "model": "flux-kontext-pro",
    "vram": "24GB",
    "latency_ms": 0.0,
    "reason": "GPU cluster is not configured (set BROBOND_RUNPOD_API_KEY and BROBOND_RUNPOD_ENDPOINT)"
  }
}
```

Três decisões:

1. **Nunca 500.** Toda saída de `gpu_health()` é um dicionário, inclusive a do
   `except Exception` final. Um readiness que estoura não informa nada além de
   que o próprio readiness quebrou.
2. **Nunca gate de deploy.** GPU ausente é capacidade ausente, não deploy
   quebrado: os três gates que decidem o 503 continuam sendo `database`,
   `migrations` e `storage`. Uma API sem cluster serve todas as rotas que não
   renderizam.
3. **Rápido.** A sonda usa deadline próprio de 5s e **uma** tentativa. Três
   retries transformariam 5s em 15s num endpoint morto, e quem consulta
   readiness já repete — consultando de novo.

### Composição com a detecção local

O bloco `gpu` existe desde a ETAPA 9 reportando `nvidia-smi` (`backend`,
`message`). PR011 **não o substitui**, compõe: quem consegue renderizar de
fato nomeia o `provider` (cluster primeiro, host depois), a sonda completa do
cluster fica em `gpu.cluster`, e `backend`/`message` continuam onde a shell os
lê. Um payload dizendo `available: false` com uma placa CUDA na máquina seria
simplesmente falso.

---

## 8. Testes (ETAPA 7)

| Arquivo | Testes | Foco |
| --- | --- | --- |
| `backend/tests/gpu_fakes.py` | — | máquina de estados que finge a API RunPod |
| `backend/tests/test_gpu_client.py` | 64 | transporte, retry, poll, cancel, transfer, segredo |
| `backend/tests/test_runpod_flux.py` | 54 | as 5 operações, payload, ciclo completo, falhas |
| `backend/tests/test_runpod_wan.py` | 50 | modos, duração/fps/seed, camera motion, falhas |
| `backend/tests/test_gpu_health.py` | 29 | readiness, composição, executor ponta a ponta, frontend |

**Cobertura medida dos cinco módulos novos: 100%** (633 statements, 0 misses),
acima do piso de 98% pedido pela etapa.

O mock é completo: `FakeRunPod` responde `/run`, `/status/{id}`,
`/cancel/{id}` e `/health`, e um job passa de verdade por
`IN_QUEUE → IN_PROGRESS → COMPLETED`, senão o polling nunca seria exercitado.
O relógio também é falso, então um deadline de 300s é testado em microssegundos
e a suíte não ganha um segundo de wall time.

---

## 9. Definition of Done

| Item | Estado |
| --- | --- |
| Director AI intacto | ✅ nenhum arquivo em `core/director*` tocado |
| Storyboard intacto | ✅ nenhum arquivo de storyboard tocado |
| Prompt Compiler intacto | ✅ |
| Provider Registry público intacto | ✅ `ProviderCapabilities` com os mesmos 8 campos; defaults ainda `flux-dev`/`wan-2.1-t2v` |
| Render Engine usando só `GenerationExecutor` | ✅ `backend/app/render/` não mudou |
| GPU detectável pelo readiness | ✅ bloco `gpu` com provider/model/vram/latency |
| Zero secrets no frontend | ✅ teste varre `app/`, `lib/`, `components/` |
| Cobertura ≥ 98% | ✅ 100% nos cinco módulos |

Os conectores novos são **registros adicionais**, não substituições: os
defaults do registry continuam apontando para os conectores locais, e um
deployment adota o cluster pedindo `runpod-flux` / `runpod-wan` pelo id.

### O diff, arquivo a arquivo

Cinco arquivos novos em `backend/app/providers/`, cinco testes novos, e
exatamente cinco arquivos existentes tocados:

| Arquivo existente | O que mudou |
| --- | --- |
| `core/config.py` | as quatro variáveis novas, todas com default vazio/seguro |
| `main.py` | um import e uma linha `body["gpu"] = readiness_gpu_block(body.get("gpu"))` |
| `providers/provider_registry.py` | duas chamadas `register(...)` em `create_default_registry()` — o ponto de extensão documentado desde o PR007 ("adicionar um backend é um registro, não um `if`"). Nenhuma assinatura, nenhum default e nenhum campo público mudaram. |
| `providers/timeout_manager.py` | os ids novos herdando os deadlines Flux/Wan já existentes |
| `providers/__init__.py` | re-exports |

`backend/app/core/director*`, `backend/app/core/storyboard_engine.py`,
`backend/app/core/prompt_compiler.py` e `backend/app/render/` **não aparecem
no diff**.
