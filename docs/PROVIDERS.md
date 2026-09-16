# PR007 — GPU Provider Orchestrator

PR007 cria uma arquitetura universal para Providers. A regra central é:

> O Core produz `GenerationSpec`; quem conhece Flux, Wan, Mock, Hunyuan, Kling, Runway ou
> qualquer SDK/checkpoint é a camada `backend/app/providers/`, nunca `backend/app/core/`.

Nenhuma imagem é gerada durante health/discovery e nenhum segredo é exposto pela API.

> **PR009 evoluiu esta camada** — os adapters Flux e Wan viraram conectores reais e o
> `GenerationExecutor` ganhou retry (máx. 3 tentativas), timeout configurável,
> fallback com motivo registrado no Job e telemetria por execução. Ver
> `docs/AI_CONNECTORS.md`.

---

## Interface única

Arquivo:

```text
backend/app/providers/base_provider.py
```

Contrato obrigatório:

```python
class BaseProvider(ABC):
    def capabilities(self) -> ProviderCapabilities: ...
    def generate_image(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset: ...
    def generate_video(self, spec: GenerationSpec, output_dir: str | Path) -> ProviderAsset: ...
    def upscale(self, spec: GenerationSpec, asset_path: str | Path, output_dir: str | Path) -> ProviderAsset: ...
    def health(self) -> ProviderHealth: ...
    def estimate(self, spec: GenerationSpec) -> ProviderEstimate: ...
```

Todos os métodos são abstratos na base. `generate_image`, `generate_video`, `upscale` e
`estimate` recebem `GenerationSpec`; não existe entrada por prompt string solto nem por
`parameters` arbitrário.

### ProviderCapabilities

Cada Provider declara:

- `max_resolution`;
- `supports_video`;
- `supports_image`;
- `supports_lora`;
- `supports_upscale`;
- `supports_seed`;
- `supports_negative_prompt`;
- `prompt_budget`.

`prompt_budget` fica na camada de provider. O Core usa orçamento conservador por padrão e só
recebe um número já resolvido pela borda.

### ProviderEstimate

`ProviderEstimate` descreve uma execução antes de rodar:

- `provider_id`;
- `kind`;
- `estimated_seconds`;
- `cost_units`;
- `notes`.

---

## Registry universal

Arquivo:

```text
backend/app/providers/provider_registry.py
```

Responsabilidades:

- `register()`;
- `get()`;
- `list()`;
- `health_all()`.

O registry usa registros e aliases, não `if/else` por nome de modelo. Adicionar outro Provider é
adicionar um `ProviderRegistration` com uma factory.

Providers registrados por padrão:

| Label | ID | Papel |
| --- | --- | --- |
| Flux | `flux-dev` | adapter local de imagem via wrapper universal |
| Wan | `wan-2.1-t2v` | adapter local de vídeo via wrapper universal |
| Mock | `mock` | provider fake para testes e desenvolvimento sem GPU |
| Hunyuan | `hunyuan-video` | adapter de vídeo carregado por registro, não por branch no executor |

A UI do PR007 destaca Flux, Wan e Mock, mas a arquitetura já aceita outros registros.

---

## Adapters

### Flux

Arquivo:

```text
backend/app/providers/flux_provider.py
```

`FluxProvider` implementa `BaseProvider` e encapsula o adapter diffusers existente. A chamada
universal é:

```python
FluxProvider().generate_image(spec, output_dir)
```

O método recebe apenas `GenerationSpec`. `generate_video` e `upscale` recusam explicitamente a
operação porque esse adapter não declara suporte.

### Wan

Arquivo:

```text
backend/app/providers/wan_provider.py
```

`WanProvider` implementa `BaseProvider` por meio de uma classe compartilhada para adapters de
vídeo diffusers, evitando duplicação de lógica. A chamada universal é:

```python
WanProvider().generate_video(spec, output_dir)
```

`generate_image` e `upscale` recusam explicitamente a operação.

### Mock

Arquivo:

```text
backend/app/providers/mock_provider.py
```

`MockProvider` retorna imagem fake, vídeo fake e upscale fake. Ele existe para testes e nunca
deve ser removido: permite validar Registry, Executor e API sem GPU, pesos ou credenciais.

---

## Generation Executor

Arquivo:

```text
backend/app/providers/generation_executor.py
```

Fluxo:

```text
GenerationSpec
  -> ProviderRegistry
  -> BaseProvider
  -> ProviderAsset
  -> ProviderJob
```

`GenerationExecutor` escolhe pelo registry e decide apenas pelo `GenerationKind` (`image` ou
`video`). Ele não conhece nomes de providers/modelos.

A fila (`backend/app/queue.py`) mantém as regras legadas de resolução/validação de catálogo, mas
a execução final passa pelo executor universal.

---

## Capability Discovery e Health

Endpoint novo:

```http
GET /api/v1/providers
```

Resposta por provider:

```json
{
  "id": "mock",
  "label": "Mock",
  "status": "ready",
  "latency_ms": 0.03,
  "version": "mock-provider-v1",
  "capabilities": {
    "max_resolution": "1024",
    "supports_video": true,
    "supports_image": true,
    "supports_lora": true,
    "supports_upscale": true,
    "supports_seed": true,
    "supports_negative_prompt": true,
    "prompt_budget": 1200
  },
  "reason": null,
  "loaded": true
}
```

A resposta não inclui tokens, secrets, URLs assinadas, chaves de storage ou variáveis de ambiente.
Health não executa geração de mídia.

---

## Frontend

Página criada:

```text
/studio/providers
```

Mostra:

- Flux;
- Wan;
- Mock;
- status;
- latência;
- versão;
- capacidades;
- botão **Testar** para recarregar health/discovery.

Arquivo principal:

```text
app/studio/providers/page.tsx
```

O client usa `listProviders()` em `lib/api.ts`, que consome `/api/v1/providers`.

---

## Testes

Arquivo novo:

```text
backend/tests/test_pr007_provider_orchestrator.py
```

Cobertura:

- `BaseProvider` e métodos abstratos;
- payloads `ProviderCapabilities`, `ProviderEstimate`, `ProviderAsset`, `ProviderHealth`;
- `ProviderRegistry.register/get/list/health_all`;
- `MockProvider`;
- `FluxProvider`;
- `WanProvider`;
- `GenerationExecutor`;
- endpoint `GET /api/v1/providers`;
- garantia de que o Core não contém nomes de catálogo/modelo de provider.

Também foram atualizados testes existentes de prompt budget: orçamentos específicos agora vêm de
`ProviderCapabilities`, não do Core.

---

## Definition of Done

- Core desacoplado de nomes de providers.
- Registry universal funcional.
- Mock Provider presente e testado.
- Flux Adapter no contrato universal.
- Wan Adapter no contrato universal, sem duplicar lógica de vídeo.
- Health endpoint público e sem segredos.
- Frontend `/studio/providers` pronto.
- Build e coverage gates verdes.
