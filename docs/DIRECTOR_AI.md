# DIRECTOR AI ENGINE — PR005

O **Director AI Engine** transforma linguagem humana em um plano cinematográfico completo, sem chamar providers e sem renderizar imagem ou vídeo.

## Escopo

- Entrada humana: intenção, persona, plataforma, duração e mood.
- Saída: `ProductionPlan` imutável com storyboard de 4 a 8 cenas.
- Não altera `backend/app/providers/*`.
- Não cria jobs de geração.
- Não grava arquivos de mídia.

## Estrutura

```text
backend/app/core/director/
├── __init__.py
├── camera_director.py
├── director_agent.py
├── mood_config.py
├── mood_engine.py
├── production_plan.py
└── shot_plan.py
```

A configuração de mood fica em `mood_config.py`; a lógica de resolução fica em `mood_engine.py`. Isso evita números e presets mágicos espalhados pelo código.

## Fluxo

```text
Intent
  ↓
Mood
  ↓
Style
  ↓
Shot Sequence
  ↓
Storyboard
  ↓
Prompt Compiler
  ↓
ProductionPlan
```

O `PromptCompiler` é usado apenas para preparar o texto planejado de cada cena. O resultado continua sendo planejamento; nenhum provider é importado ou executado.

## ProductionPlan

`ProductionPlan` é uma dataclass congelada (`frozen=True`) e, portanto, imutável após criada.

Campos:

- `id`
- `title`
- `concept`
- `mood`
- `audience`
- `platform`
- `duration`
- `style`
- `music`
- `voice`
- `persona_id`
- `shots`
- `created_at`

`shots` contém apenas `ShotPlan` e deve ter ao menos uma cena.

## ShotPlan

Cada cena do storyboard carrega todos os campos obrigatórios:

- `scene_number`
- `title`
- `objective`
- `emotion`
- `camera`
- `lens`
- `lighting`
- `motion`
- `duration`
- `prompt`
- `negative_prompt`
- `environment`

O plano responde, por cena:

| Pergunta | Campo |
| --- | --- |
| O que acontece? | `prompt` / ação compilada |
| Por que existe? | `objective` |
| Qual emoção? | `emotion` |
| Qual câmera? | `camera` + `motion` |
| Quanto tempo? | `duration` |

## Moods internos

Presets oficiais:

- `Luxury`
- `Epic`
- `Dark`
- `Minimal`
- `Sport`
- `Neo`

Cada preset define:

- LUT
- contraste
- iluminação
- temperatura
- ritmo
- partículas

Aliases em português e inglês são resolvidos pelo `MoodEngine`; mood desconhecido cai em `Minimal`.

## Camera Director

`CameraDirector` consome a `ShotLibrary` existente e escolhe movimentos editáveis:

- Dolly
- Orbit
- Crane
- Tracking
- Static
- Drone

A câmera escolhida é uma decisão inicial. A UI deixa o usuário editar câmera, lente, duração, objetivo e emoção depois da criação do plano.

## Método principal

```python
create_production_plan(user_intent, persona_id, platform, duration, *, mood=None)
```

Os quatro primeiros parâmetros são a entrada obrigatória do PR005. `mood` é uma preferência
opcional da UI; sem ela, o `MoodEngine` infere a atmosfera a partir de `user_intent`.

## API

```http
POST /api/v1/core/director/production-plan
```

Payload:

```json
{
  "user_intent": "Criar um comercial épico para tênis de corrida",
  "persona_id": "persona-123",
  "platform": "youtube",
  "duration": 45,
  "mood": "Epic"
}
```

Resposta: `DirectorProductionPlanResponse`, com o `ProductionPlan` e seus `shots`.

## Frontend

Página criada:

```text
/studio/director
```

Controles:

- campo grande: **"O que você quer criar hoje?"**
- Persona
- Plataforma
- Duração
- Mood
- botão **"Criar Produção"**

A tela renderiza cards de storyboard com:

- Cena
- Objetivo
- Câmera
- Lente
- Duração
- Emoção

No PR006, a mesma rota alimenta um `StoryboardState` versionado no cliente, com canvas,
timeline, inspector e painéis de câmera/mood. A página continua sem chamar geração de imagem
nem vídeo.

## Testes

Cobertura adicionada em `backend/tests/test_pr005_director_ai.py`:

- `DirectorAgent`
- `MoodEngine`
- `CameraDirector`
- `ProductionPlan`
- `ShotPlan`
- Storyboard de 4 a 8 cenas
- Rota de production plan
- UI `/studio/director`
- Garantia de ausência de job/output de render
- Garantia de que providers não são importados pelo Director AI Engine
