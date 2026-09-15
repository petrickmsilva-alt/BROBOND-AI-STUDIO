# Project Memory (PR004.1)

O contrato oficial de memória de projeto do estúdio. Hoje a persistência é
`localStorage`; amanhã será PostgreSQL. **O objeto é exatamente o mesmo nos
dois mundos** — por isso o formato está congelado aqui e só muda com
migration.

---

## 1. Contrato (`ProjectMemoryState`)

Definido em `lib/memory/project_memory.ts`. `projectId` é o **único campo
obrigatório**; todos os outros são opcionais.

| Campo | Tipo | Significado |
| --- | --- | --- |
| `projectId` | `string` *(obrigatório)* | Projeto dono do estado |
| `workspaceId` | `string \| null` | Tenant do projeto (conhecido quando há persona ativa) |
| `personaId` | `string \| null` | Persona ativa (id do perfil do PR003) |
| `wardrobeId` | `string \| null` | Seleção de wardrobe. Hoje: nomes dos itens, join compacto `,` (o estúdio ainda não tem id por item); futuro: id da entrada de wardrobe |
| `styleId` | `string \| null` | Estilo em uso. Hoje: o nome do estilo; futuro: id do estilo no catálogo |
| `loraId` | `string \| null` | Última versão de LoRA escolhida (asset id) |
| `cameraPreset` | `string \| null` | Preset de câmera do Video Studio (`static/pan/tilt/zoom/tracking/crane`) |
| `aspectRatio` | `string \| null` | Proporção em uso (`16:9` / `9:16` / `1:1`) |
| `lastPrompt` | `string \| null` | Último texto de prompt (restaurado no textarea) |
| `lastPlatform` | `string \| null` | Última plataforma usada (`image` / `video`) |
| `duration` | `number \| null` | Duração do vídeo em segundos (`5` / `10` / `15`) |
| `updatedAt` | `string \| null` | ISO-8601 do último save (carimbo do adapter) |

### Regras do contrato

1. **Nunca muda sem migration.** Campo novo = envelope com nova `v` +
   função de migration aqui neste módulo. O cliente (hook/componentes) não
   é reescrito.
2. Campos desconhecidos em disco são **descartados** na desserialização
   (forward compatibility: um campo de versão futura não vaza para o
   cliente).
3. Tipos errados viram `absente` (ex.: `duration: "10"` string → ignorado).
4. O objeto é **serializável JSON puro** — requisito para a coluna JSONB
   futura.

---

## 2. Adapter (`lib/memory/project_memory.ts`)

A **única fronteira de storage do frontend**. É o único arquivo do
repositório que referencia `window.localStorage` (guarda estrutural em
`backend/tests/test_project_memory_contract.py`).

### API pública (estável entre backends)

```ts
loadProjectMemory(projectId: string): ProjectMemoryState | null
saveProjectMemory(state: ProjectMemoryState): ProjectMemoryState
clearProjectMemory(projectId: string): void
```

- `loadProjectMemory` → `null` quando: sem memória para o projeto, sem
  browser (SSR), storage bloqueado, JSON corrompido ou versão desconhecida.
  Nunca lança.
- `saveProjectMemory` carimba `updatedAt` e devolve o estado gravado.
- `clearProjectMemory` remove apenas o projeto endereçado; os demais não
  sofrem.

### A chave oficial

Existe **uma** chave oficial: `PROJECT_MEMORY_KEY = 'brobond_project_memory'`.
Nenhum componente ou módulo conhece a string — ela vive só no adapter.
Formato em disco (hoje, browser):

```jsonc
// PROJECT_MEMORY_KEY
{
  "v": 1,
  "projects": {
    "brobond-project-01": { "projectId": "...", "personaId": "...", "updatedAt": "...", ... }
  }
}
```

Uma chave, muitos projetos. O envelope (`v` + `projects`) é detalhe de
transporte do localStorage; **o objeto por projeto é o contrato** e é o que
viaja para o PostgreSQL.

### Migration de versão (único ponto documentado)

- `v` ausente + campos legacy → **v0 → v1** (shape plana do PR004):
  `persona_id → personaId`, `last_lora → loraId`, `default_style → styleId`,
  `selected_wardrobe → wardrobeId` (join). Executa uma vez (write-through).
- `v` conhecido mas diferente da atual → **recusa a leitura** (sem perda
  silenciosa, sem chute) e o documento bruto permanece intocado. Essa é a
  ramificação onde entra o próximo migrator.

### Seams de storage adjuntos (mesmo módulo, contratos separados)

O adapter é a fronteira de storage **do frontend inteiro**, então os demais
acessos a `localStorage` também passam por ele — como funções nominais, com
suas próprias chaves, **não fazendo parte do `ProjectMemoryState`**:

- `getAuthToken()` / `setAuthToken(token)` / `clearAuthToken()` — token de
  sessão do PR002 (chave `AUTH_TOKEN_KEY`), consumido por `lib/api.ts`.
- `setLegacyPersonaId(id)` — chave legacy `brobond_persona_id` escrita pelo
  Persona Lab (superseded pela `personaId` do contrato; mantida porque
  Legacy nunca é deletado, Bible §2).

---

## 3. Hook (`lib/memory/use_project_memory.ts`)

```ts
const { memory, save, clear } = useProjectMemory(projectId);
```

- **Somente consome o adapter.** Não toca storage, não conhece a chave, não
  serializa nada.
- `memory` é carregada **sincronamente** no primeiro render (a leitura do
  localStorage é síncrona) — sem efeito, sem race com o primeiro save.
- `save(patch)` = **atualização parcial**: shallow merge sobre o estado
  atual + `projectId` + `updatedAt`, e persiste.
- `clear()` remove a memória do projeto (estado + storage).

---

## 4. Como o estúdio usa (sem mudança visual)

- `app/page.tsx` (Home) chama `useProjectMemory(PROJECT_ID)` — é o **único**
  lugar que conhece o projeto. Nenhum componente conhece a chave de
  armazenamento.
- Restauração (uma vez, quando memória + catálogo de personas estão
  prontos): persona ativa, estilo, wardrobe, LoRA, câmera, proporção,
  duração e último prompt voltam aos seus controles.
- Persistência: a cada mudança do estado criativo, `save({...})` com o
  `ProjectMemoryState` completo — o mesmo objeto que o PostgreSQL servirá.
- `cameraPreset` / `aspectRatio` / `duration` agora são owned pelo Home
  (mesmos controles, mesmos defaults, zero mudança visual) para que o
  contrato possa persisti-los.

---

## 5. Migração futura para PostgreSQL

O swap é **server-side**; o cliente não muda.

1. Tabela (esboço — nenhum schema existente é alterado):

   ```sql
   CREATE TABLE project_memory (
     project_id  TEXT PRIMARY KEY,
     workspace_id TEXT REFERENCES workspaces(id),
     state       JSONB NOT NULL,   -- ProjectMemoryState, exatamente como hoje
     version     INT   NOT NULL,   -- == PROJECT_MEMORY_VERSION (hoje: 1)
     updated_at  TIMESTAMPTZ NOT NULL
   );
   ```

2. Um endpoint (ex.: `GET/PATCH /api/v1/project-memory/{project_id}`,
   autenticado e tenant-scoped como o resto do PR003) lê/escreve `state`.
3. O adapter troca o corpo de `loadProjectMemory` / `saveProjectMemory` /
   `clearProjectMemory` por chamadas HTTP **mantendo a mesma assinatura** —
   o hook e os componentes ficam intocados. A fallback para
   `localStorage` pode permanecer offline (mesma regra de honestidade: sem
   API, o estúdio avisa).
4. Versionamento: `version` na linha espelha o `v` do envelope; o migrator
   desta página vira o migrator da coluna.

**Por que o objeto não muda:** todo campo do contrato é JSON puro e já tem
significado independente do backend. `wardrobeId`/`styleId` são hoje
nomes/join — quando o backend introduzir ids reais, a migration é de
*valor*, não de *shape*.

---

## 6. O que é Legacy (marcado, nunca deletado)

- `lib/projectMemory.ts` (v0, PR004): **sem call sites live** desde o
  PR004.1. Mantido para imports antigos continuarem resolvendo; delega ao
  adapter e não toca storage diretamente (guardado por teste).

## 7. Testes

- **Comportamentais** (vitest, `lib/memory/*.test.ts(x)`, gate de
  cobertura **95%**): persistência, serialização, desserialização,
  atualização parcial, clear, compatibilidade de versão (v0→v1, versão
  futura, JSON corrompido), seams SSR/bloqueadas e o hook
  (`memory`/`save`/`clear`).
- **Estruturais** (backend, `test_project_memory_contract.py`): nenhum
  componente toca `localStorage`; um único arquivo referencia
  `window.localStorage`; uma única chave oficial; o contrato tem
  exatamente os campos da spec; o hook consome apenas o adapter; o CI roda
  a suíte de contrato.
