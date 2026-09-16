# PR006 — Storyboard Cinematic Engine

PR006 transforma o storyboard do Director AI em um editor cinematográfico visual.
Ele continua dentro do limite aprovado do BROBOND AI STUDIO: **planejamento e edição apenas**.
Nenhum Provider é alterado, nenhuma imagem é renderizada e nenhum job de geração é criado.

---

## Entidade central

`StoryboardState` é o estado versionado do editor:

```text
project_id
production_plan_id
scenes[]
version
updated_at
```

Toda operação real cria um novo estado, incrementa `version` e recalcula a timeline.
Operações sem efeito — por exemplo mover uma cena para ela mesma — retornam o mesmo estado.

No backend, a entidade vive em:

```text
backend/app/core/director/storyboard_state.py
```

No frontend, o estado operacional do editor vive em:

```text
lib/storyboard/storyboard_state.ts
```

A UI inicializa o `StoryboardState` a partir do `ProductionPlan` criado pelo PR005.

---

## Cena editável

Cada cena do editor preserva o plano cinematográfico e permite edição granular de:

- título;
- objetivo;
- emoção;
- câmera;
- lente;
- iluminação;
- movimento;
- duração;
- ambiente.

A edição não recria a cena inteira: ela aplica um patch no campo escolhido, mantém `id`,
`prompt`, `negative_prompt`, mood e LUT quando eles não fazem parte da operação.

---

## Drag & Drop

`StoryboardCanvas` usa drag-and-drop nativo do navegador para reordenar cenas.
Ao soltar uma cena sobre outra, o editor:

1. move o item no array `scenes[]`;
2. recalcula `scene_number` começando em 1;
3. recalcula `timeline_start` e `timeline_end`;
4. mantém a duração total quando apenas a ordem muda;
5. persiste o resultado no `StoryboardState` com `version + 1`.

---

## Camera Panel

O painel lateral `CameraPanel` oferece presets:

- Hero Walk;
- Orbit;
- Tracking;
- Crane;
- Drone;
- Static.

Selecionar um preset altera somente o bloco de direção de câmera da cena:
`camera`, `lens`, `lighting` e `motion`. Objetivo, emoção, ambiente, mood, LUT e prompts
permanecem intactos.

---

## Mood Panel

`MoodPanel` permite mood por cena:

- Luxury;
- Epic;
- Dark;
- Minimal;
- Sport;
- Neo.

A seleção altera apenas `mood` e `lut` no plano editável. Isso não chama Providers e não
recompila prompts. A LUT é tratada como metadado de planejamento.

---

## Timeline

`Timeline` é horizontal e mostra cada cena como bloco proporcional à duração:

```text
C1  C2  C3  C4 ...
```

Cada cena expõe um controle deslizante para ajuste de duração. Ao arrastar o controle:

1. a duração da cena muda;
2. `timeline_start` e `timeline_end` são recalculados em todas as cenas afetadas;
3. a duração total é recalculada por `totalDuration(state)`;
4. o estado versionado é atualizado.

---

## Undo / Redo

`StoryboardHistory` mantém histórico das operações de edição com limite de 50 estados.
Operações cobertas:

- editar;
- reordenar;
- duplicar;
- remover.

`undo` move o estado atual para `future` e restaura o último estado de `past`.
`redo` move o próximo estado de `future` de volta para `present`.

---

## Duplicate Scene

Duplicar uma cena:

- cria uma nova cena imediatamente após a original;
- atribui novo UUID/ID;
- mantém câmera, lente, iluminação e movimento;
- mantém mood e LUT;
- recalcula `scene_number` e timeline;
- incrementa `version`.

---

## Frontend desacoplado

A página `/studio/director` foi reorganizada em componentes independentes:

```text
app/studio/director/
├── StoryboardCanvas.tsx
├── Timeline.tsx
├── SceneInspector.tsx
├── CameraPanel.tsx
├── MoodPanel.tsx
└── page.tsx
```

Responsabilidades:

| Componente | Responsabilidade |
| --- | --- |
| `StoryboardCanvas` | renderizar cards, seleção, drag/drop, duplicar e remover |
| `Timeline` | mostrar C1/C2/C3/C4 proporcionalmente e editar duração por arraste |
| `SceneInspector` | editar os campos granulares da cena selecionada |
| `CameraPanel` | aplicar presets de direção de câmera |
| `MoodPanel` | aplicar mood e LUT por cena |
| `page.tsx` | orquestrar API PR005, `StoryboardState` e histórico |

---

## API

PR006 não adiciona rota de renderização. O fluxo continua:

```http
POST /api/v1/core/director/production-plan
```

A resposta `ProductionPlan` alimenta o `StoryboardState` local/versionado no editor.
`docs/API.md` registra explicitamente que PR006 edita o plano e não executa geração.

---

## Testes

Cobertura adicionada:

- backend: `backend/tests/test_pr006_storyboard_engine.py`;
- frontend: `lib/storyboard/storyboard_state.test.ts`.

Casos cobertos:

- Timeline;
- Drag/reorder;
- Undo;
- Redo;
- Duplicate;
- Version;
- Scene Update;
- Camera Panel;
- Mood Panel;
- limite de 50 estados no histórico.

---

## Definition of Done

- Nenhum Provider alterado.
- Storyboard versionado.
- Drag funcionando.
- Timeline funcionando.
- Undo/Redo implementado.
- Duplicate Scene implementado.
- Frontend desacoplado.
- Sem geração de imagem.
- Sem regressão nos contratos existentes.
