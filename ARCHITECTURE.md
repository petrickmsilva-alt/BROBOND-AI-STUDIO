# BROBOND AI STUDIO — ARCHITECTURE

## Camadas

```text
Frontend/       Next.js, TypeScript, design system, workspace UX
Backend/        FastAPI, auth, REST, WebSocket, orchestration
Core/           memory, prompt engine, director, policy, roadmap
AI Engine/      provider adapters for FLUX, Wan, Hunyuan, ControlNet, IP Adapter
Render Engine/  Celery, Redis, GPU workers, FFmpeg, queue lifecycle
Database/       PostgreSQL, SQLAlchemy, Alembic, workspace metadata
Assets/         MinIO, signed URLs, local development adapter
Knowledge Base/ Cinematic Bible, style, characters, shots, prompts, presets
```

## BROBOND CORE

O Core é a camada de decisão. Ele consulta a Knowledge Base, resolve memória de persona, combina preset cinematográfico, expande o prompt e entrega um `GenerationSpec` versionado ao Render Engine.

```text
User Intent
  -> Director Agent
  -> Memory Resolver
  -> Prompt Composer
  -> GenerationSpec
  -> Provider Adapter
  -> Queue / GPU Worker
  -> Asset + Event Stream
```

## Agentes

- **CEO Agent:** prioridade, escopo, impacto no roadmap.
- **CTO Agent:** arquitetura, segurança, contratos e qualidade.
- **Director Agent:** roteiro, linguagem cinematográfica, ritmo e câmera.
- **ML Agent:** provider, VRAM, LoRA, ControlNet e inferência.
- **UX Agent:** fluxo, clareza, feedback e acessibilidade.

Agentes são responsabilidades lógicas e podem começar como serviços determinísticos. A evolução para modelos separados não deve alterar os contratos do Core.

## Contratos importantes

- `GenerationSpec`: prompt estruturado, memória, preset, condicionadores e output.
- `Job`: estado, progresso, logs, cancelamento e output.
- `Asset`: arquivo, tipo, workspace, versão e origem.
- `PersonaMemory`: identidade fixa, LoRAs, roupas, voz e autorização.
- `ShotPreset`: código, câmera, lente, movimento, luz e ritmo.

## Regras de isolamento

Providers nunca acessam diretamente componentes React. Rotas nunca contêm lógica de inferência. A Knowledge Base é somente leitura durante geração e versionada durante edição. Jobs longos nunca rodam na thread HTTP.
