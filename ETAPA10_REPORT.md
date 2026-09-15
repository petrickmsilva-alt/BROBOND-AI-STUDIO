# ETAPA 10 — PROVIDER ADAPTERS

**Data:** 2026-09-15
**Branch:** `arena/01a0a25e-brobond-ai-studio`
**Base:** `37087845aa2638f436f38a75c9ac914700d8f94e`
**Escopo:** tornar reais os "adapters substituíveis" que `SYSTEM_PROMPT.md` declara, sem duplicar código e sem tocar em `DirectorAgent`.

---

## 1. Resumo

`SYSTEM_PROMPT.md` diz: *"FLUX, Wan, Hunyuan, ControlNet, IP Adapter e futuros providers são
adapters substituíveis."* A auditoria mostrou que isso **não era verdade**: não havia como
substituir nada.

| Métrica | Antes | Depois |
|---|---|---|
| Testes | 548 | **605** (+57) |
| Providers no catálogo com adapter | 2 de 4 | **3 de 4** (`flux-1.1-pro-ultra` é remoto por definição) |
| Cobertura de `backend/app` | 83% | **85%** |
| `providers/registry.py` | — | **100%** (61 stmts) |
| `providers/conditioning.py` | — | **100%** (42 stmts) |
| Implementações duplicadas entre providers | **4** | **0** |
| Rotas HTTP `/api/v1` | 52 | **54** |
| Paths com tag `core` | 25 | **27** |
| Arquivos deletados vs. baseline | — | **0** |

Nenhum arquivo foi removido. `_supported_kwargs`, `_generator`, `pipeline_arguments` e
`_dimensions` continuam importáveis de `image.py` e `video.py`, porque são superfície testada.

---

## 2. Auditoria — o que foi medido antes de escrever código

**2.1 — O dispatch era por tipo de job, nunca por provider.**

```python
# backend/app/queue.py, antes
if job.type == GenerationType.IMAGE:
    provider = FluxDiffusersProvider(...)   # qualquer que fosse spec.provider
else:
    provider = WanVideoProvider(...)        # qualquer que fosse spec.provider
```

**2.2 — `resolve_model_id` devolve o fallback FLUX para quase tudo.** Medido:

```
flux-dev         -> black-forest-labs/FLUX.1-dev
wan-video        -> black-forest-labs/FLUX.1-dev     <- pedido de vídeo vira FLUX
hunyuan-video    -> black-forest-labs/FLUX.1-dev
controlnet       -> black-forest-labs/FLUX.1-dev
desconhecido     -> black-forest-labs/FLUX.1-dev
None             -> black-forest-labs/FLUX.1-dev
```

6 de 7 entradas caem no mesmo repositório. E no caminho de vídeo, pedir `hunyuan-video`
devolvia `wan-2.1-t2v` — **Wan, sem nenhum erro**.

**2.3 — A API anunciava um provider inexistente.** `GET /api/v1/models/video` já devolvia
`{"id": "hunyuan-video", "status": "planned-provider"}`. O catálogo era honesto; o código
atrás dele não existia.

**2.4 — `CONSUMED_SPEC_FIELDS` mentia.** Medido por análise estática:

```
FLUX declarado          : aspect_ratio, controlnet, guidance_scale, lora, prompt_compiled,
                          reference_path, resolution, seed, steps
FLUX usado em args      : guidance_scale, negative_prompt, prompt_compiled, seed, steps
USADO NÃO DECLARADO     : ['negative_prompt']
```

O teste existente (`test_consumed_fields_are_declared_and_really_exist`) só verificava
`declarado ⊆ campos do spec` — nunca se o declarado batia com o que o código consome. Por
isso passou.

**2.5 — O IP-Adapter carregava pesos SDXL num pipeline FLUX.**

```python
pipeline.load_ip_adapter("h94/IP-Adapter", weight_name="ip-adapter-plus_sdxl_vit-h.safetensors")
```

Verificado contra a documentação do diffusers para `FluxPipeline`, que especifica
`XLabs-AI/flux-ip-adapter`, `weight_name="ip_adapter.safetensors"` e
`image_encoder_pretrained_model_name_or_path="openai/clip-vit-large-patch14"`. Numa máquina
com GPU a chamada antiga falharia no load.

**2.6 — Quatro implementações duplicadas.** Medido por comparação de `inspect.getsource`:

| Helper | Resultado |
|---|---|
| `_generator` | **idêntico** (151 chars nos dois arquivos) |
| `_apply_lora` | **idêntico** |
| `health()` | idêntico salvo o nome do provider |
| `_supported_kwargs` | idêntico salvo o docstring (6 linhas de diferença, todas docstring) |

**2.7 — ControlNet era um `raise` dentro do provider FLUX.** A mensagem estava certa
(ControlNet exige `FluxControlPipeline`), mas o formato errado: uma surpresa em tempo de
execução em vez de uma decisão de roteamento.

**2.8 — Defeito meu, da ETAPA 9.** `PROVIDER_PROMPT_BUDGET` usava a chave `"wan-video"`, que
**não é id do catálogo** (o real é `"wan-2.1-t2v"`). Medido:

```
ids do catalogo       : flux-1.1-pro-ultra, flux-dev, hunyuan-video, wan-2.1-t2v
chaves do budget (ET9): flux-dev, hunyuan-video, wan-video
chaves que NAO sao id : ['wan-video']
ids sem budget        : ['flux-1.1-pro-ultra', 'wan-2.1-t2v']
```

Um job de vídeo real caía no orçamento conservador de 1000 em vez de 1200.

---

## 3. O que foi construído

### 3.1 Registry

```text
job.parameters["model"]  ->  registry.resolve(id, kind)  ->  registry.check(entry, kind)
                                     |                              |
                            ProviderEntry                     recusa ANTES de carregar
                            (kind, status,                    planned / remoto / kind errado
                             module, attribute,
                             model_id, conditioning)
                                     |
                            registry.adapter_class(entry)   <- getattr em tempo de chamada
```

A classe é resolvida por `getattr` **no momento da chamada**. Não é detalhe de estilo: os
testes do worker fazem `monkeypatch.setattr(image_module, "FluxDiffusersProvider", Fake)`, e
uma referência capturada no import venceria o patch. Verificado por
`test_the_class_is_resolved_late_so_a_test_can_patch_it`.

Um provider **recusado** é diferente de um provider **substituído**. `check()` falha alto para
planejado, remoto ou kind errado.

### 3.2 Hunyuan

`HunyuanVideoProvider` compartilha `_DiffusersVideoProvider` com Wan e difere só onde os
modelos de fato diferem:

| | Wan 2.1 | Hunyuan |
|---|---|---|
| pipeline | `WanPipeline` | `HunyuanVideoPipeline` |
| frames (fps 24 × 5s) | **121** (4n+1) | **120** (sem restrição) |
| 16:9 padrão | 832×480 | 1280×720 |
| `num_inference_steps` | não enviado | enviado (`spec.steps`) |

A regra de frames **não** foi unificada de propósito: aplicar 4n+1 ao Hunyuan mudaria a
duração do clipe em silêncio.

### 3.3 Uma definição para o que era quatro

`providers/common.py` agora é a única casa de `supported_kwargs`, `generator_for`,
`apply_lora`, `health_report`, `cuda_availability` e `require_cuda`. Os módulos os
reexportam — verificado que são o **mesmo objeto**, não cópias:

```
image._supported_kwargs is common.supported_kwargs : True
video._supported_kwargs is common.supported_kwargs : True
image._generator is common.generator_for           : True
video._generator is common.generator_for           : True
Wan tem _apply_lora próprio?                       : False  (herdado)
Wan tem health próprio?                            : False  (herdado)
```

### 3.4 Conditioning como objeto

`Conditioning` declara o que precisa (`pipeline_class`, `weights`, `argument`), e
`IpAdapterWeights` existe especificamente para impedir que pesos de um modelo base sejam
aplicados a outro — que foi o bug encontrado.

### 3.5 Rotas

`GET /api/v1/core/providers` (catálogo: kind, status, checkpoint, conditioning; filtrável por
`kind`) e `GET /api/v1/core/providers/health` (se cada adapter local pode rodar nesta máquina
agora; nunca lança).

---

## 4. Erros meus, encontrados por teste

**4.1 — Copiei a declaração errada ao criar o Hunyuan.** `HunyuanVideoProvider.arguments`
consome `spec.steps`, mas a primeira versão copiava `CONSUMED_SPEC_FIELDS` do Wan, que não
inclui `steps`. É **exatamente** a classe de defeito que esta etapa remove, reintroduzida por
mim na mesma etapa. Pegou pela análise estática; corrigido com
`VIDEO_CONSUMED_SPEC_FIELDS | frozenset({"steps"})}`.

**4.2 — A primeira versão da análise estática só olhava dentro de classes.** `pipeline_arguments`
do `image.py` é função de nível de módulo, então o teste não via `negative_prompt` e falhava
por motivo errado. Corrigido para varrer classes **e** funções de módulo que recebem `spec`.

**4.3 — `GenerationKind` não estava importado no `main.py`.** A rota de catálogo subiu e
quebrou com `NameError` no primeiro filtro por `kind`. Descoberto ao exercitar a rota, não ao
escrevê-la.

**4.4 — Tentei herdar `CONSUMED_SPEC_FIELDS` da base de vídeo**, que não tinha esse atributo:
`AttributeError: type object '_DiffusersVideoProvider' has no attribute 'CONSUMED_SPEC_FIELDS'`.
Içado para a constante de módulo `VIDEO_CONSUMED_SPEC_FIELDS`.

---

## 5. Verificação de que a guarda não é vazia

Um teste que não pode falhar não vale nada. O bug original foi **reintroduzido de propósito**
(removendo `negative_prompt` da declaração do FLUX) e o teste falhou:

```
bug reintroduzido
FAILED test_provider_adapters.py::test_the_declared_fields_match_the_code
1 failed

--- restaurado ---
53 passed
```

---

## 6. Fronteiras preservadas

| Fronteira | Teste |
|---|---|
| O worker entrega só o spec ao provider | `test_the_worker_hands_the_image_provider_only_a_spec` (pré-existente, intacto) |
| Nenhum provider aceita string de prompt | `test_no_provider_accepts_a_prompt_string_or_a_parameters_dict` (pré-existente) |
| As rotas não escolhem adapter | `test_the_provider_routes_contain_no_selection_logic` (AST sobre `main.py`) |
| O knob `settings.video_model_id` continua valendo | `test_the_worker_still_defaults_to_wan_when_no_model_is_named` |
| O knob não vaza para o Hunyuan | `test_the_settings_video_knob_does_not_leak_into_hunyuan` |
| `resolve_model_id` não inventa repositório | `test_resolve_model_id_never_invents_a_repository` (pré-existente, intacto) |
| `spec.provider` mantém a semântica da ETAPA 3 | `test_the_worker_needs_no_fallback_because_the_adapter_already_resolved_it` (pré-existente) |

`DirectorAgent` **não foi editado** — continua sendo território da ETAPA 7, que está em aberto.

---

## 7. Verificação

Todos os comandos foram executados; os números abaixo são as saídas reais.

```
PYTHONPATH=backend pytest backend/tests -q                    -> 605 passed
pytest backend/tests -q          (hermético, sem PYTHONPATH)  -> 605 passed
pytest <arquivos em ordem inversa>                            -> 605 passed
pytest <13 arquivos do baseline 3708784>                      -> 22 passed
pytest backend/tests/test_core_independence.py                -> 17 passed
coverage report --include=*/providers/registry.py             -> 61 stmts, 0 miss, 100%
coverage report --include=*/providers/conditioning.py         -> 42 stmts, 0 miss, 100%
coverage report --include=*/providers/*                       -> 303 stmts, 50 miss, 83%
coverage report --include=backend/app/*                       -> 3210 stmts, 481 miss, 85%
npm run build                                                 -> ✓ Compiled successfully
git diff --diff-filter=D --name-only 3708784                  -> vazio (0 removidos)
```

Caminhos de código efetivamente exercitados: `registry.resolve/check/build/adapter_class/register/unregister`,
`common.apply_lora/generator_for/cuda_availability/require_cuda/health_report`,
`conditioning.resolve_controlnet/resolve_reference/apply_ip_adapter/controlnet_arguments`,
`FluxDiffusersProvider._apply_conditioning`, `HunyuanVideoProvider.arguments`,
`queue.process_generation` (roteamento real, com refusals) e as duas rotas novas.

**O que não pôde ser verificado aqui:** `torch` e `diffusers` **não estão instalados** neste
sandbox. Portanto `_load()` e `generate()` — os caminhos que de fato chamam um pipeline — não
foram executados. As 50 linhas descobertas de `providers/` são exatamente essas. Os ids de
modelo foram conferidos contra a documentação pública do diffusers
(`hunyuanvideo-community/HunyuanVideo` com `HunyuanVideoPipeline`; `XLabs-AI/flux-ip-adapter`
com `ip_adapter.safetensors`), não contra uma execução real.

---

## 8. Achados documentados, não remendados

**8.1 — `spec.provider` mistura dois namespaces.** Id de repositório para imagem
(`"black-forest-labs/FLUX.1-dev"`) e id de catálogo para vídeo (`"wan-2.1-t2v"`). É
comportamento deliberado da ETAPA 3, fixado por
`test_the_worker_needs_no_fallback_because_the_adapter_already_resolved_it`. **Não alterado.**
O registry despacha pelo id lógico vindo de `job.parameters["model"]`, então a inconsistência
não atrapalha o roteamento — mas continua sendo uma armadilha para quem ler o spec.

**8.2 — `resolve_model_id` devolve o fallback FLUX para todo id desconhecido.** Preservado por
`test_resolve_model_id_never_invents_a_repository`. O registry cobre o caso por cima, mas a
função em si segue permissiva.

**8.3 — `VIDEO_CONSUMED_SPEC_FIELDS` é um nome de módulo, não um contrato.** Se um terceiro
adapter de vídeo aparecer com um conjunto muito diferente, a constante vai precisar virar
outra coisa. Registrado como dívida pequena e consciente.

**8.4 — `flux-1.1-pro-ultra` continua sem adapter local.** É `remote-provider` por definição e
agora é recusado explicitamente em vez de cair no FLUX local. Implementá-lo exige a ETAPA 12
ou um client de API remota, fora do escopo.

---

## 9. Documentação atualizada

`CHANGELOG.md` (bloco `[Unreleased] — ETAPA 10`), `ARCHITECTURE.md` (nova seção "Provider
adapters (ETAPA 10)" + 6 guardas na tabela + 2 rotas na fronteira de API), `ROADMAP.md` (item
marcado), `README.md` (contagens, seção "Provider adapters", suítes), `backend/README.md`
(contagens, seção "Provider adapters", módulos a 100%).

---

## 10. Pendências

Herdadas e não resolvidas: **ETAPA 7 (Director AI) inteira** — bloqueada por falha de
infraestrutura no sandbox quando foi pedida; P0-2b persistência de `Job`; ledger de persona em
memória; bibliotecas em memória; P0-3 `hub.publish` sem chamadores; P0-4 endpoints sem
autorização; UI não consome as rotas Core; `next@14.2.32` com CVE conhecida;
`minio`/`python-jose` declarados sem uso em caminho vivo; motivação `transformation` com 2 de
300 presets; arco `documentary` inalcançável e ciclo de objetivos em `_build_beats` (ambos
dependem da ETAPA 7); adjetivos soltos vindos de campos verbatim e `describe()` sem chamador
em produção (ETAPA 9).

Novas desta etapa: `flux-1.1-pro-ultra` sem adapter local (8.4) e
`VIDEO_CONSUMED_SPEC_FIELDS` como constante de módulo (8.3).
