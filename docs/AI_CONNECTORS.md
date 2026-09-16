# PR009 — Real AI Connectors

PR009 liga os adapters de provider (PR007) a motores reais de geração — Flux para
imagem e Wan 2.1 para vídeo — e envolve o `GenerationExecutor` com três camadas de
resiliência: **retry**, **timeout** e **fallback**, mais **telemetria** por execução.

As regras de PR007 continuam valendo sem exceção:

- Provider recebe **apenas `GenerationSpec`** — nunca prompt solto nem `dict` de
  parâmetros. O conector monta seu request tipado (`FluxRequest`/`WanRequest`)
  direto do spec.
- O Core não conhece marcas de provider. Toda menção a Flux/Wan/Hunyuan vive em
  `backend/app/providers/`.
- O Director AI, o Storyboard e o Render Engine **não foram tocados**: o Render
  Orchestrator continua chamando `GenerationExecutor.execute(spec, output_dir, ...)`
  exatamente como antes. O que mudou é como `execute` sobrevive a falhas.

Documentação das camadas anteriores: `docs/PROVIDERS.md` (PR007) e
`docs/RENDER_ENGINE.md` (PR008).

---

## 1. Conectores reais

### Flux — imagem (`providers/flux_provider.py`)

| Modo do spec | Pipeline | Observação |
| --- | --- | --- |
| `text-to-image` | `FluxPipeline` | altura/largura via `dimensions_for(aspect_ratio, resolution)` |
| `image-to-image` | `FluxImg2ImgPipeline` | exige `spec.reference_path`; sem referência é `ValueError` (falha **fatal**, não retry) |

Suportado: `seed`, `negative_prompt`, `steps`, `lora` (via `apply_lora`, compartilhado
em `providers/common.py`), `aspect_ratio`. O pipeline é carregado **por modo** e
cacheado (`_pipeline_mode`), com CPU offload (`enable_model_cpu_offload`) — um modelo
de ~24 GB não fica inteiro na VRAM.

Se `diffusers`/`torch` não estiverem instalados, `generate_image` levanta
`ProviderUnavailable` ("diffusers/torch are not installed"). Sem CUDA,
`ProviderUnsupported` ("CUDA GPU is required"). Ambas são honestas: nada finge sucesso.

O loader (`FluxPipelineLoader`) é uma costura de teste: testes injetam pipelines fake
e o conector inteiro é exercitado sem GPU. Em produção o loader importa
`diffusers` tarde (dentro da chamada), nunca no import do módulo.

### Wan — vídeo (`providers/wan_provider.py`)

| Modo do spec | Pipeline | Observação |
| --- | --- | --- |
| `text-to-video` | `WanPipeline` | frames calculados como `duration × fps`, arredondados para `4n+1` |
| `image-to-video` | `WanImageToVideoPipeline` | exige `spec.reference_path`; frame inicial carregado como PIL |

Suportado: `duration`, `fps`, `motion_strength` (campo tipado do spec, padrão `1.0`,
aceito pela classe `WanPipeline`), `seed`, `aspect_ratio`. Os frames são codificados
com `imageio` (`libx264`) no FPS declarado — se `imageio` faltar, `RuntimeError`
retryável. As capabilities declaram explicitamente o que é consumido e o que é
ignorado (`declared_consumed`/`declared_unsupported`), então a UI pode mostrar
limites reais em vez de prometer.

Hunyuan (`hunyuan-video`) permanece registrado e compartilha o mesmo loader de vídeo;
modo `image-to-video` nele é recusado como unsupported (o pipeline Hunyuan não expõe
essa entrada).

---

## 2. Retry (`providers/retry_policy.py`)

```python
policy = RetryPolicy(max_attempts=3)          # padrão: 3 tentativas
engine = RetryEngine(policy)                  # sleeper injetável (testes não dormem)
outcome = engine.run(callable, provider_id=...)
```

Classificação de erro (`RetryEngine.classify`):

| Estado | Erros | Consequência |
| --- | --- | --- |
| `RETRYABLE` | `ProviderUnavailable`, `ConnectionError`, `OSError`, `TimeoutError`, `imageio` faltando | nova tentativa com backoff |
| `TIMEOUT` | `ProviderTimeoutError` | nova tentativa com backoff |
| `FATAL` | `ProviderUnsupported`, `ValueError`, `KeyError` (não registrada), tudo que não é transitório | para imediatamente, sem fallback por retry |

Backoff: `min(base_delay * 2^(attempt-1), max_delay)` (1s → 2s → 4s, cap 8s).
Máximo de **3 tentativas** por execução — constante do produto, testada.

O executor decide o que fazer com o resultado (`RetryOutcome`):

- **sucesso** → segue para telemetria;
- **exauriu retryable/timeout** → fallback (se habilitado), motivo registrado;
- **fatal** → re-levanta com telemetria registrada (`error_code="fatal"`), sem
  fallback mascarar erro de spec inválido.

---

## 3. Timeout (`providers/timeout_manager.py`)

Cada provider tem um deadline de parede (segundos) configurável por ENV:

| Provider | Padrão | ENV override |
| --- | --- | --- |
| Flux (`flux-dev`, `flux-1.1-pro-ultra`) | **90s** | `PROVIDER_TIMEOUT_FLUX_SECONDS` |
| Wan (`wan-2.1-t2v`) | **300s** | `PROVIDER_TIMEOUT_WAN_SECONDS` |
| Hunyuan (`hunyuan-video`) | **300s** | `PROVIDER_TIMEOUT_HUNYUAN_SECONDS` |
| qualquer outro | **120s** | `PROVIDER_TIMEOUT_DEFAULT_SECONDS` |

`TimeoutManager.run(fn)` executa `fn` num worker e espera até o deadline. Se estourar,
levanta `ProviderTimeoutError` (retryável). Ajuste fino por instância via
`TimeoutSettings`/`deadline_for(provider_id)`. Timeout **0 ou negativo desliga** o
deadline para aquele provider.

Limite conhecido e declarado: GPU não é preemptível — o deadline encerra a **espera**
do executor, não o kernel em execução no hardware. Isso está nos docstrings e em
`docs/LIMITATIONS.md`.

---

## 4. Fallback

Fluxo completo dentro de `GenerationExecutor.execute`:

```text
resolve provider no Registry
  falhou (não registrado / kind errado)?
      -> fallback imediato, motivo "provider ... not registered"
  RetryEngine.run(provider.generate_*, com TimeoutManager)
      sucesso                    -> asset
      exauriu retryable/timeout  -> fallback, motivo com causa original
      FATAL                      -> re-levanta (sem fallback)
```

Regras invioláveis:

- **O Batch nunca se perde.** O Render Orchestrator roda cena a cena; a cena que
  caiu em fallback vira um asset do `MockProvider` (com `aspect_ratio` respeitado,
  passando no Quality Gate) e o batch continua. Teste dedicado força 6 falhas em
  2 cenas e o batch fecha `completed`.
- **O motivo fica no Job.** `ProviderJob.fallback=True`, `fallback_from` (provider
  pedido), `fallback_reason` (texto com a causa) — visíveis em `/api/v1/jobs/{id}`.
- **O provider real fica no ProviderJob** (`provider_id` = quem de fato rodou, ex.
  `mock`), então a telemetria nunca atribui trabalho ao provider errado.
- Fallback pode ser desligado (`GenerationExecutor(..., enable_fallback=False)`):
  nesse caso o erro vira `ProviderUnavailable` com motivo e telemetria registrados.
- Erro **fatal nunca cai em fallback** — spec inválido não é problema de provider.

---

## 5. Telemetria (`providers/telemetry.py`)

Toda execução — sucesso, fallback ou falha — registra um
`ProviderTelemetryRecord` com os seis campos do produto:

| Campo | Fonte |
| --- | --- |
| `provider_id` | quem executou de fato (ou o pedido, se nem rodou) |
| `latency_ms` | tempo total da chamada `execute` |
| `queue_time_ms` | `latency − render` (nunca negativo) |
| `render_time_ms` | soma do tempo de parede das tentativas sob timeout |
| `success` | `bool` |
| `error_code` | `timeout` / `unavailable` / `unsupported` / `generation-error` / `not-registered` / `fatal` / `None` |

Mais `kind`, `attempts`, `fallback`, `fallback_from`, `timestamp`.

`TelemetryStore`: deque thread-safe (cap 500, mais novo primeiro), sink JSONL opcional
(`PROVIDER_TELEMETRY_LOG_PATH`) que engole `OSError` — telemetria nunca derruba
geração. `default_telemetry_store()` é singleton lazy;
`reset_default_telemetry_store()` existe como costura de teste.

Rotas (ambas públicas por desenho, sem segredos expostos):

- `GET /api/v1/providers/telemetry?limit=N` — histórico mais-novo-primeiro (1–500, padrão 50);
- `POST /api/v1/providers/{provider_id}/test` — roda um spec determinístico contra o
  provider e devolve `ProviderTestResult` (status `passed`/`fallback`/`failed`,
  latência, tentativas, motivo). É o "Teste Real" da tela `/studio/providers`.

---

## 6. Frontend — `/studio/providers`

A página mantém tudo do PR007 (latência, capabilities, versão, orçamento) e ganha:

- **Disponibilidade** — badge `ready`/`unavailable` derivado do health real;
- **Último Health** — timestamp do último check (`last_health_at`);
- **Teste Real** — botão que chama `POST /providers/{id}/test` e mostra o resultado
  com honestidade: sucesso, fallback (com motivo e provider substituto) ou falha.

Nenhuma geração acontece ao abrir a página; o teste só roda quando pedido.

---

## 7. Testes

`backend/tests/test_pr009_ai_connectors.py` — **81 testes**, pacote
`backend/app/providers/` a **100%** de cobertura:

- estados e cap de 3 tentativas da RetryEngine, classificação, backoff com cap, hook de decisão;
- defaults do TimeoutManager (90/300/300/120), overrides por ENV e por settings,
  expiração de deadline e desligamento com 0;
- telemetria: campos, cap do store, JSONL (incl. sink quebrado), 6 códigos de erro;
- conectores Flux/Wan com pipelines fake injetados (fake `torch`/`diffusers` no
  `sys.modules`, padrão ETAPA 16) — modos, guards de referência, args de pipeline,
  recusas sem diffusers/CUDA/imageio;
- fallback do executor: provider ausente, kind errado, retry exaurido, timeout,
  fatal propagado com telemetria, fallback desligado, e o batch que sobrevive a 6
  falhas via `RenderOrchestrator`;
- rotas novas (`/test`, `/telemetry`) e guards de arquitetura (Core sem marcas,
  spec como única entrada).

---

## 8. Limitações honestas

- Sem GPU/pesos no CI: os testes exercitam os conectores com pipelines fake. O
  primeiro render GPU real continua sendo o marco `[ ] Primeiro render GPU
  validado ponta a ponta` do ROADMAP.
- Timeout limita espera, não compute (GPU não preemptível).
- `motion_strength` é aceito pelos pipelines Wan; o efeito depende do checkpoint.
- Telemetria é em memória (deque) — suficiente para diagnóstico; persistência é
  evolução futura.
