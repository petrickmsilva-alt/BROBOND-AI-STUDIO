# BROBOND AI STUDIO

> Um estúdio privado, local-first, para transformar direção criativa em imagens, movimento e personagens consistentes.

O BROBOND AI STUDIO é a fundação de uma plataforma de mídia generativa inspirada na fluidez de ferramentas como Kling, mas desenhada para uso local, controle de dados e evolução futura para SaaS. O repositório separa o produto visual (Next.js) da API de orquestração (FastAPI), com contratos que permitem conectar engines de GPU sem acoplar o produto à implementação de um único modelo.

## O que já está disponível

### Frontend

- Dashboard premium em dark mode com Overview, fila de render e projetos recentes.
- Image Studio com prompt editor, negative prompt, ratios, resolução, steps, CFG, seed, modelo, personagem, referência e ações de variação/upscale.
- Video Studio com Text to Video, Image to Video e Start + End Frame, duração, FPS, aspect ratio, câmera, modo cinematográfico e áudio nativo.
- Personas com treinamento LoRA, conjunto de fotos, identidade, âncoras visuais e score de consistência.
- Motion Control com presets de câmera, caminho visual, keyframes e fine tuning.
- Storyboard com premissa, quatro cenas conectadas e prompts editáveis por cena.
- Assets e Projects com filtros, biblioteca e status.
- Settings com monitor de VRAM, cache local, privacidade e preferências.
- Interações de produto funcionais: navegação entre módulos, geração simulada, feedback de fila, upload de referência e toasts de ação.

### Backend

- FastAPI com OpenAPI em `/docs` e `/redoc`.
- API versionada em `/api/v1`.
- Login local com JWT em `/api/v1/auth/login`, pronto para ser conectado a um repositório de usuários PostgreSQL.
- Health check, status de GPU, fila, geração de imagem/vídeo, prompt enhancement e storyboard.
- WebSocket de fila em `/api/v1/ws/queue`.
- `GenerationService` isolado dos providers: Diffusers, Torch, FLUX, Wan/Hunyuan e Celery podem ser conectados sem reescrever as rotas.
- Docker Compose para API, PostgreSQL, Redis e MinIO.
- Testes de contrato para health check e prompt engine.

## Requisitos

- Node.js 20+
- npm 10+
- Python 3.12+ para o backend (Python 3.11 também funciona no ambiente de desenvolvimento atual)
- Docker Desktop opcional para subir a infraestrutura local

## Rodar o frontend

```bash
npm install
npm run dev
```

Abra <http://localhost:3000>.

Para produção local:

```bash
npm run build
npm start
```

## Rodar a API

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Abra <http://localhost:8000/docs> para o Swagger.

Se estiver usando Python 3.11, substitua `python3.12` por `python3`.

## Infraestrutura local

```bash
docker compose up --build
```

Serviços:

| Serviço | Porta | Uso |
| --- | ---: | --- |
| Next.js | 3000 | Interface |
| FastAPI | 8000 | API e documentação |
| PostgreSQL | 5432 | Persistência futura de projetos, assets e usuários |
| Redis | 6379 | Fila e eventos |
| MinIO | 9000 / 9001 | Object storage e console |

Copie `.env.example` para `.env` antes de customizar credenciais locais. Nunca coloque chaves reais no Git.

## Estrutura

```text
.
├── app/
│   ├── globals.css
│   ├── layout.tsx
│   └── page.tsx
├── components/
│   └── studio-shell.tsx
├── backend/
│   ├── app/
│   │   ├── api/routes.py
│   │   ├── core/config.py
│   │   ├── schemas/generation.py
│   │   ├── services/generation.py
│   │   └── main.py
│   ├── tests/test_health.py
│   ├── Dockerfile
│   └── requirements.txt
├── docker-compose.yml
├── .env.example
├── package.json
└── tailwind.config.ts
```

## Próximas integrações de produção

1. Adicionar autenticação JWT e isolamento por `workspace_id`.
2. Persistir jobs, projetos, personas e assets com SQLAlchemy + Alembic.
3. Trocar o `QueueService` em memória por Celery + Redis e eventos WebSocket via pub/sub.
4. Implementar adapters de Diffusers/FLUX para imagem e Wan/Hunyuan para vídeo.
5. Adicionar pipeline de FFmpeg H.264, export 720p–4K e thumbnails no MinIO.
6. Criar worker de treino LoRA com validação de dataset, captions e monitor de VRAM.
7. Conectar o frontend aos endpoints relativos da API através de proxy Next.js, sem chamadas a `localhost` no browser em deploy.
8. Adicionar RBAC, auditoria, backups e criptografia de secrets para a versão SaaS.

## Princípios de arquitetura

- **Provider agnostic:** modelos são adapters, não regras de negócio.
- **Local first:** prompts, imagens e jobs podem permanecer na máquina do usuário.
- **API contracts first:** schemas Pydantic documentam o acordo entre UI, API e workers.
- **SOLID:** cada serviço possui uma responsabilidade clara e pode ser substituído por uma implementação de produção.
- **Graceful degradation:** a interface pode ser explorada sem GPU; os serviços reais entram atrás da mesma fila.

## Testes

Frontend:

```bash
npm run build
```

Backend:

```bash
cd backend
pytest
```
