# BROBOND AI STUDIO — ARCHITECTURE MANIFEST

**PR010.0 — Platform Freeze.** Este documento é a declaração oficial da
arquitetura da plataforma. Ele não descreve uma intenção: descreve o que o
código faz hoje, e o que o código **não pode** passar a fazer.

Antes do AI Core, a arquitetura é congelada. Nenhuma feature nova, nenhuma
alteração visual, nenhuma mudança funcional — apenas contratos e guardas.

A tabela de cada módulo é lida por
[`backend/tests/test_architecture_boundaries.py`](../backend/tests/test_architecture_boundaries.py).
As dependências abaixo não são prosa: são a fonte da verdade que o teste
executa contra o grafo real de imports. Editar este documento sem editar o
código (ou o contrário) deixa a CI vermelha.

---

## Como ler este manifesto

Cada módulo declara quatro coisas:

| Campo | Significado |
| --- | --- |
| **Owner** | Quem responde pelo módulo. Uma mudança de fronteira precisa desta assinatura. |
| **Responsabilidade** | A única coisa que o módulo faz. Se a frase precisa de "e", o módulo provavelmente tem dois donos. |
| **Dependências permitidas** | O conjunto **completo** do que o módulo pode importar. Não é exemplo, é allow-list. |
| **Dependências proibidas** | Acoplamentos que a plataforma recusa por desenho, com o motivo. |

Duas regras valem para todos:

1. **Contratos são a única língua entre módulos.** Um módulo importa
   `app.contracts` (ETAPA 4) e fala com o resto por meio dele. Trocar
   dataclasses ad-hoc entre pacotes é acoplamento disfarçado de conveniência.
2. **Proibido é transitivo.** Não vale contornar a regra importando um terceiro
   que importa o proibido. O guard calcula o fecho transitivo do grafo, então
   um caminho indireto falha exatamente como um `import` direto.

O grafo real, medido no código de hoje, está em
[Grafo congelado](#grafo-congelado) no fim do documento.

---

## Mapa de propriedade

O nome do módulo neste manifesto é um nome de domínio, não um diretório. Esta
tabela é a tradução — é ela que o guard usa para classificar cada arquivo:

| Módulo | Pacotes Python |
| --- | --- |
| **AI Core** *(future)* | `app.ai_core` *(ainda não existe — reservado)* |
| **Director AI** | `app.core.director`, `app.core.director_agent` |
| **Storyboard Engine** | `app.core.storyboard_engine`, `app.core.timeline` |
| **Render Engine** | `app.render` |
| **Provider Registry** | `app.providers` |
| **Campaign Builder** | `app.campaign` |
| **Quality Engine** | `app.quality`, `app.core.quality` |
| **Persona Engine** | `app.core.persona_memory`, `app.core.memory_resolver`, `app.repositories.persona_repository` |
| **Database Guard** | `app.core.database_guard` |
| **Network Layer** | `lib/network/` *(frontend — TypeScript)* |
| Contracts | `app.contracts`, `app.core.contracts` |
| Prompt Compiler | `app.core.prompt_compiler`, `app.prompt_engine` |
| Cinematic Knowledge | `app.core.cinematic_library`, `app.core.shot_library`, `app.core.shot_resolver`, `app.core.style_resolver`, `app.knowledge`, `app.conditioning` |
| Spec Builder | `app.core.generation_spec_builder`, `app.spec_adapter` |
| Job Queue | `app.core.job_service`, `app.job_service`, `app.jobs`, `app.store`, `app.queue`, `app.events`, `app.repositories` |
| Continuity Engine | `app.continuity` |
| Knowledge Graph | `app.graph` |
| Asset Library | `app.assets` |
| Storage | `app.storage`, `app.media`, `app.preprocessing`, `app.training`, `app.lora` |
| Persistence | `app.db`, `app.models` |
| Security | `app.auth`, `app.audit` |
| Runtime Config | `app.core.config`, `app.system`, `app.readiness` |
| Application Boundary | `app.main`, `app.schemas`, `app.provider_capabilities` |
| Dead Cluster | `app.api`, `app.services`, `app.core.security` |
| Package Root | `app`, `app.core` |

Os dez primeiros são os módulos que o PR010.0 manda declarar. Os demais existem
no código e são declarados aqui porque uma allow-list com buracos não é uma
allow-list: sem eles o guard não conseguiria afirmar que **todo** arquivo do
backend tem dono.

---

## AI Core *(future)*

| Campo | Valor |
| --- | --- |
| **Owner** | CTO — BROBOND AI STUDIO |
| **Status** | **Não implementado.** Reservado por este manifesto. |
| **Responsabilidade** | Será a camada de raciocínio que compõe os módulos existentes: recebe intenção, consulta Director, Storyboard, Quality e Render, e decide. Nenhuma linha existe hoje. |
| **Dependências permitidas** | Todos os módulos. É o **único** com esse direito. |
| **Dependências proibidas** | Nenhuma — mas ver a regra abaixo. |

**Por que o único que pode conhecer todos.** Um orquestrador precisa enxergar
as peças que orquestra. O risco é o inverso: se qualquer módulo puder importar
o AI Core, o grafo vira um ciclo e a fronteira deixa de existir. Por isso a
regra é assimétrica e está congelada aqui **antes** de a primeira linha ser
escrita:

> **Nenhum módulo pode importar o AI Core.** O AI Core chama; ele não é
> chamado por Director, Storyboard, Render, Providers, Campaign, Quality ou
> Persona.

O guard já protege `app.ai_core` hoje, com o pacote ainda inexistente. No dia
em que ele for criado, a fronteira já estará valendo — que é exatamente o ponto
de congelar antes.

---

## Director AI

| Campo | Valor |
| --- | --- |
| **Owner** | CTO — BROBOND AI STUDIO |
| **Responsabilidade** | Intenção em linguagem natural → direção: conceito, roteiro, cenas, câmera, mood, duração. Produz **significado**, nunca texto de prompt e nunca mídia. |
| **Dependências permitidas** | Contracts, Prompt Compiler, Cinematic Knowledge |
| **Dependências proibidas** | **Provider Registry**, Render Engine, Quality Engine, Campaign Builder, Persistence, Storage, Job Queue, Application Boundary |

**Director NÃO importa Providers** — regra explícita do PR010.0. O Diretor
decide *o que* filmar; qual GPU, qual checkpoint e qual adapter executam é
decisão do Registry. Se o Diretor conhecesse providers, o planejamento passaria
a depender do hardware instalado, e o plano deixaria de ser reprodutível. O
guard `test_pr007` já proíbe o Core de sequer *nomear* marcas de provider; aqui
a proibição vira estrutural.

O Prompt Compiler é permitido porque `core/director/director_agent.py` compõe
blocos — e o Compiler é o único lugar do sistema onde texto de prompt nasce.

---

## Storyboard Engine

| Campo | Valor |
| --- | --- |
| **Owner** | CTO — BROBOND AI STUDIO |
| **Responsabilidade** | Escala os beats do Diretor em shots reais da biblioteca, encadeia continuidade, valida a sequência contra a Bíblia e monta a timeline. |
| **Dependências permitidas** | Contracts, Director AI, Cinematic Knowledge |
| **Dependências proibidas** | Provider Registry, Render Engine, Quality Engine, Campaign Builder, Persistence, Storage, Job Queue, Application Boundary |

Depende do Director por desenho (`storyboard_engine.py` importa
`director_agent`): ele escala o que o Diretor decidiu. A seta é de mão única —
o Diretor não conhece o Storyboard.

Não produz prompt (`test_the_engine_never_produces_prompt_text`) e não guarda
shots próprios (`test_the_engine_holds_no_shots_of_its_own`).

---

## Render Engine

| Campo | Valor |
| --- | --- |
| **Owner** | CTO — BROBOND AI STUDIO |
| **Responsabilidade** | Executa o plano: cena → `GenerationSpec` → executor → asset em disco, com progresso por push e cancel/retry por lote. |
| **Dependências permitidas** | Contracts, Prompt Compiler, Provider Registry, Storage, Persistence |
| **Dependências proibidas** | Director AI, Storyboard Engine, Quality Engine, Campaign Builder, Knowledge Graph, Continuity Engine, Application Boundary |

Importa o Registry **apenas** através do `GenerationExecutor`: o orquestrador
não conhece `provider_registry` e nenhum arquivo de `app/render/` pode
mencionar Flux, Wan, Hunyuan, Kling ou Runway
(`test_pr008_render_engine.py`). Renderizar é executar uma spec, não escolher
um modelo.

Não importa Director nem Storyboard: recebe cenas já planejadas como entrada,
via `SceneRenderInput`. É o que permite renderizar um plano vindo de qualquer
origem — inclusive, no futuro, do AI Core.

---

## Provider Registry

| Campo | Valor |
| --- | --- |
| **Owner** | CTO — BROBOND AI STUDIO |
| **Responsabilidade** | Fonte única de qual adapter roda: registro, capabilities, health, retry, timeout e telemetria. Recusa o que não pode honrar em vez de substituir em silêncio. |
| **Dependências permitidas** | Contracts, Runtime Config |
| **Dependências proibidas** | **Director AI**, Storyboard Engine, Render Engine, Quality Engine, Campaign Builder, Persona Engine, Persistence, Storage, Job Queue, Application Boundary |

**Providers NÃO importam Director** — regra explícita do PR010.0, e a metade
que faltava da simetria. Um provider recebe um `GenerationSpec` e devolve um
artefato. Se conhecesse o Diretor, passaria a interpretar intenção — e a
decisão vazaria da camada que a possui para a camada que apenas executa.

A allow-list é a mais curta da plataforma de propósito: Contracts (a spec) e
Runtime Config (timeouts e chaves por ENV). Nada mais. Um provider não lê banco
e não escreve asset — quem persiste é o Render Engine.

---

## Campaign Builder

| Campo | Valor |
| --- | --- |
| **Owner** | CTO — BROBOND AI STUDIO |
| **Responsabilidade** | Briefing → campanha completa: entregáveis, timeline, CTAs, duplicação, anexo de entregas reais e export do ZIP com manifesto. |
| **Dependências permitidas** | Contracts, Prompt Compiler, Storage, Persistence |
| **Dependências proibidas** | **Quality Engine**, Director AI, Storyboard Engine, Render Engine, Provider Registry, Knowledge Graph, Continuity Engine, Application Boundary |

**Campaign NÃO importa Quality** — regra explícita do PR010.0. Campanha é
planejamento comercial: o que será entregue, quando e em que formato. Qualidade
é o veredito sobre um artefato já renderizado. Se a campanha lesse score, um
entregável passaria a "sumir do plano" porque um render saiu com 68 — e o plano
deixaria de ser plano.

As duas superfícies se encontram no Application Boundary, que pode ler as duas
e montar a resposta HTTP. É o lugar certo: a rota compõe, os domínios não se
conhecem.

---

## Quality Engine

| Campo | Valor |
| --- | --- |
| **Owner** | CTO — BROBOND AI STUDIO |
| **Responsabilidade** | Um render entra, um veredito honesto 0–100 sai. Oito critérios ponderados, critério não medido é excluído e listado. **Recomenda, nunca executa.** |
| **Dependências permitidas** | Contracts, Persistence |
| **Dependências proibidas** | **Render Engine**, Director AI, Storyboard Engine, Provider Registry, Campaign Builder, Storage, Job Queue, Application Boundary |

**Quality NÃO importa Render** — regra explícita do PR010.0, e a que mais
protege o produto. O motor avalia fatos de mídia (`MediaFacts`: caminho,
geometria, duração, fps, prompt). Se pudesse importar o Render Engine, a
recomendação viraria execução: "score 62 → regenerar" deixaria de ser texto na
tela e passaria a disparar GPU sozinho. O sprint do V3.4 proíbe isso em prosa;
aqui a proibição passa a ser verificada.

Storage também é proibido: o engine recebe um caminho já resolvido, não vai
buscar bytes. Quem resolve é a rota.

---

## Persona Engine

| Campo | Valor |
| --- | --- |
| **Owner** | CTO — BROBOND AI STUDIO |
| **Responsabilidade** | Identidade permanente de personagem: memória versionada, aprovação governada, snapshot por episódio e relatório de drift. Identidade nunca muda em silêncio. |
| **Dependências permitidas** | Contracts, Persistence |
| **Dependências proibidas** | Director AI, Storyboard Engine, Render Engine, Provider Registry, Quality Engine, Campaign Builder, Storage, Application Boundary |

O Core lê identidade por `Protocol` (`PersonaSource`, `PersonaProfileSource`),
não por SQLAlchemy — o repositório é injetado na borda. Persistence aparece na
allow-list porque `repositories/persona_repository.py` pertence a este módulo e
é, por desenho, a **única** fronteira da persona com o banco.

---

## Database Guard

| Campo | Valor |
| --- | --- |
| **Owner** | CTO — BROBOND AI STUDIO |
| **Responsabilidade** | Provar que o banco configurado responde: abre conexão, executa `SELECT 1`, respeita timeout de 5s, fecha. Nada além disso. |
| **Dependências permitidas** | Runtime Config |
| **Dependências proibidas** | Todos os demais módulos, incluindo Persistence (`app.db`) |

Proibir `app.db` é deliberado e é o ponto do guard: ele abre uma conexão
descartável com `NullPool` e a encerra. Se usasse a `SessionLocal` da aplicação,
passaria a medir a saúde do *pool* em vez da saúde do *banco*, e um pool
saudável apontando para um Postgres morto responderia "ok".

Nunca cria tabela e nunca roda migração — schema é trabalho do Alembic.

---

## Network Layer

| Campo | Valor |
| --- | --- |
| **Owner** | CTO — BROBOND AI STUDIO |
| **Escopo** | Frontend (TypeScript), `lib/network/` |
| **Responsabilidade** | A **única** fronteira de `fetch` do frontend: timeout, retry só-GET com backoff, merge de abort, erro tipado (`NetworkErrorType`), trace id `x-brobond-trace` e detecção de cold start. |
| **Dependências permitidas** | Nenhuma. `lib/network/request.ts` não importa nada do projeto; `status.ts` importa apenas `./request`. |
| **Dependências proibidas** | `lib/api.ts`, componentes React, qualquer módulo de domínio. A seta é sempre `api → network`. |

Guardado por `test_frontend_honesty.py::test_fetch_lives_only_in_the_network_layer`:
o literal `fetch(` só pode aparecer em `lib/network/request.ts`. Foi um `catch`
indiscriminado que produziu o falso "API Offline" com a API respondendo 200
(PR009.2); a camada existe para que essa confusão não tenha onde renascer.

**PR013 (V4.0.1)** amplia o escopo com `lib/network/upload.ts`: o upload
multipart com progresso real (porcentagem, velocidade, bytes) precisa de
`XMLHttpRequest` — `fetch` não emite eventos de progresso de envio nos
navegadores-alvo. A mesma disciplina vale: nenhum componente instancia XHR,
a classe de erro é a da camada (`NetworkErrorType`) e o trace id continua a
existir. Componente nenhum ganhou uma segunda saída de rede.

---

## Asset Library

| Campo | Valor |
| --- | --- |
| **Owner** | CTO — BROBOND AI STUDIO |
| **Responsabilidade** | A biblioteca cinematográfica: ingestar uploads (PNG/JPG/WEBP/MP4/MOV) via `StorageService` com thumbnail e metadata persistidos, e servir a leitura filtrada/pesquisável da grade e do preview. |
| **Dependências permitidas** | Persistence, Storage |
| **Dependências proibidas** | Director AI, Storyboard Engine, Render Engine, Provider Registry, Quality Engine, Campaign Builder, Prompt Compiler, Application Boundary |

Introduzido pelo PR013 (V4.0.1). A fronteira é a metáfora do acervo: a
biblioteca sabe **guardar e encontrar** um asset, nunca **fazê-lo**. Ela lê as
linhas `Asset` que outros escritores já gravaram (render, conditioning,
exports — LEFT JOIN, leitura) e grava as suas (`Asset` + `AssetMetadata` do
upload) pela `StorageService` existente. Importar Providers ou Render a
faria conhecer quem produziu a mídia — acoplamento do mesmo tipo que a
regra "a biblioteca antiga não conhecia o registry" já impedia.

---

## Grafo congelado

Medido a partir do AST de `backend/app/`, não escrito à mão. É o estado que
este PR congela:

```text
Director AI          -> Contracts, Prompt Compiler, Cinematic Knowledge
Storyboard Engine    -> Contracts, Director AI, Cinematic Knowledge
Render Engine        -> Contracts, Prompt Compiler, Provider Registry, Storage, Persistence
Provider Registry    -> Contracts, Runtime Config
Campaign Builder     -> Contracts, Prompt Compiler, Storage, Persistence
Quality Engine       -> Contracts, Persistence
Persona Engine       -> Contracts, Persistence
Database Guard       -> Runtime Config
Asset Library        -> Persistence, Storage                 (PR013)
AI Core              -> (não existe)
```

As quatro proibições nomeadas pelo PR010.0 já valem hoje, direta e
transitivamente — este PR não as corrige, ele as **trava**:

| Regra | Direto | Transitivo |
| --- | --- | --- |
| Director ⇏ Providers | ok | ok |
| Quality ⇏ Render | ok | ok |
| Providers ⇏ Director | ok | ok |
| Campaign ⇏ Quality | ok | ok |

---

## O que muda quando isto muda

Este manifesto é executável. Alterar uma fronteira exige, na mesma PR:

1. editar a tabela do módulo aqui;
2. ver `test_architecture_boundaries.py` passar com a nova regra;
3. justificar no `CHANGELOG.md` por que o acoplamento passou a ser aceitável.

Não há caminho em que o código ganhe uma dependência nova e o documento fique
para trás: o teste lê o código, compara com estas tabelas e falha na diferença.

Documentos irmãos: [`EVENT_CATALOG.md`](EVENT_CATALOG.md) (os eventos oficiais),
[`API_SNAPSHOT.json`](API_SNAPSHOT.json) (a superfície pública congelada) e
[`../ARCHITECTURE.md`](../ARCHITECTURE.md) (como cada peça funciona por dentro).
