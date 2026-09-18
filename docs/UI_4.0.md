# BROBOND UI 4.0 — Cinematic Design System (PR012)

PR012 is a **UI/UX-only** redesign of the BROBOND AI Studio frontend. It does
not touch FastAPI, Providers, the Director Engine, the Storyboard Engine, the
Quality Engine, the database, any API contract, or any route. Every screen
still talks to exactly the same `lib/api.ts` functions it did before this PR;
only the presentation layer changed.

Goal: an interface at the premium standard of Runway + Linear + DaVinci
Resolve — luxury, cinematic, minimal, premium, fast, dark. Never pure white,
never pure black.

## ETAPA 1 — Design tokens

`lib/theme/tokens.ts` is the single source of truth for color, typography,
motion and layout. It is pure data (zero backend dependency) and is mirrored
as CSS custom properties in `app/globals.css` (`tokensToCssVariables()`
generates the same block programmatically for tests / future runtime
theming; the literal `:root` block is kept for zero-JS first paint).

| Token | Value |
|---|---|
| Background | `#07070A` |
| Surface | `#111113` |
| Surface 2 | `#18181B` |
| Border | `#27272A` |
| Primary | `#8B5CF6` |
| Success | `#22C55E` |
| Warning | `#F59E0B` |
| Danger | `#EF4444` |
| Text Primary | `#FAFAFA` |
| Text Secondary | `#A1A1AA` |

## ETAPA 2 — Typography

Inter Variable, six-step hierarchy (`lib/theme/tokens.ts#typography`, CSS
classes `.bb-display-xl` … `.bb-caption`):

| Level | Size | Weight |
|---|---|---|
| Display XL | 48px | Bold (700) |
| H1 | 34px | Bold (700) |
| H2 | 26px | Semibold (600) |
| H3 | 20px | Semibold (600) |
| Body | 15px | Regular (400) |
| Caption | 12px | Medium (500) |

## ETAPA 3 — Sidebar Premium

`components/studio/sidebar.tsx`, wired into `app/page.tsx`.

- Fixed width **248px** (`layout.sidebarWidth`), never fluid.
- Three groups: **CREATE** (Director, Storyboard, Render Queue), **STUDIO**
  (Personas, Image, Video, Campaigns), **LIBRARY** (Assets, Knowledge,
  Continuity, Quality).
- Badges are restricted to **GPU / SQL / AI** only (`isAllowedBadge`); any
  other badge is silently dropped by the component itself — the old
  `GRAPH` / `V3.2` / `V3.3` / `V3.4` badges are gone from the product.
- The old sidebar "Readiness" panel is removed; the Status Dock (ETAPA 6)
  is now the single source of system health.

## ETAPA 4 — Hero Workspace

`components/studio/hero-workspace.tsx`, replacing the Director's two empty
panels in `app/page.tsx`.

- **Left — Creative Brief:** textarea, scene count, language, platform and
  one primary action ("Criar Produção"), wired to the existing
  `directIntent()` call.
- **Right — Live Storyboard Preview:** scene thumbnails rendered from
  `DirectorBrief.beats` the moment a brief comes back, using cinematic
  gradient placeholders (`.bb-hero-preview-thumb-0..5`) when no render
  exists yet — the workspace never looks empty.

## ETAPA 5 — Identity Bar

`components/studio/identity-bar.tsx`, always visible above the Hero
Workspace in the Director view: avatar, persona name, style, LoRA, palette
swatches and a "Ready" status pill. Reads the same `activePersona` / `style`
/ `selectedLora` / `loras` state `app/page.tsx` already owned.

## ETAPA 6 — Status Dock

`components/studio/status-dock.tsx` + `lib/theme/status_mapping.ts`.

- Bottom bar, **max 52px** height (`layout.statusDockHeight`), replacing the
  lateral "Readiness" list.
- Six indicators, fixed order: **API, Database, Storage, GPU, FLUX, WAN**,
  each colored dynamically (`online` = success green, `degraded` = warning
  amber, `offline` = danger red, `unknown` = text-secondary grey).
- `buildStatusDockIndicators({ readiness, gpu, providers, apiOnline })` is a
  pure function over the exact same `readiness()`, `gpuInfo()` and
  `listProviders()` reads `app/page.tsx` already performs — no new backend
  surface.

## ETAPA 7 — Storyboard Cards

`components/studio/storyboard-cards.tsx`, wired into
`app/studio/director/page.tsx` in place of the previous `StoryboardCanvas`.

- Each scene renders as a card: Thumbnail (cinematic placeholder when no
  render exists), Cena, Objetivo, Lente, Câmera, Duração, Mood.
- Drag/drop reorder plugs into the existing `reorderScene()` /
  `StoryboardState` wiring, unchanged.
- Duplicate/remove actions moved to the `SceneInspector` header (the
  cinematic card no longer carries a per-card action row).

## ETAPA 8 — Motion

`lib/theme/tokens.ts#motion` — subtle, never flashy:

- Hover transitions: **120ms**, `cubic-bezier(0.2, 0.8, 0.2, 1)`.
- Card hover scale: exactly **1.01** (`.bb-story-card:hover`).
- Buttons gain elevation on hover (`.bb-primary-button:hover` — soft
  purple shadow, `translateY(-1px)`), never a bounce or flash.
- Sidebar fade: 180ms opacity transition on collapse.

## ETAPA 9 — Responsive breakpoints

`lib/theme/tokens.ts#breakpoints`: Desktop 1440, Laptop 1024, Tablet 768,
Mobile 480. `app/globals.css` media queries under each breakpoint keep the
Director usable at every size (hero workspace stacks to one column at
1024px, sidebar becomes an overlay at 768px, identity fields collapse to
essentials at 480px).

## ETAPA 10 — Accessibility

- Every `bb-*` interactive element has a visible `:focus-visible` outline
  (`--bb-primary`, 2px, offset).
- Landmarks and ARIA: `role="list"`/`"listitem"` on cards, `role="status"`
  on the identity pill and Status Dock, `aria-current="page"` on the active
  sidebar item, `aria-label` on every panel that isn't otherwise named by a
  visible heading.
- Full keyboard navigation: storyboard cards are focusable
  (`tabIndex={0}`) and respond to Enter/Space exactly like a click.
- Color is never the only signal: the Status Dock also exposes a
  visually-hidden state string per indicator (`.bb-visually-hidden`).

## Testing

`components/studio/{sidebar,hero,storyboard_cards,status_dock,identity_bar}.test.tsx`
plus `lib/theme/{tokens,status_mapping}.test.ts` cover the new design system
and its five presentational components. Full suite: `npx vitest run`
(14 files / 191 tests, all green). Coverage gate: `npx vitest run --coverage`
— **99.91% statements / 99.28% branch / 98.75% functions / 99.91% lines**,
above the required 98% threshold.

## What was verified vs. what could not be verified in this sandbox

- ✅ `npm run build` (Next.js production build) — compiles cleanly, 12
  static pages generated, no type errors introduced by this PR.
- ✅ `npx vitest run --coverage` — green, ≥98% on every metric.
- ✅ Server-rendered HTML for `/` and `/studio/director` confirmed the new
  `bb-sidebar`, `bb-identity-bar`, `bb-hero-workspace` and `bb-status-dock`
  markup is present and the dev server returns `200` with no runtime
  errors in the logs.
- ⚠️ **Lighthouse Desktop ≥95 could not be measured in this sandbox** — no
  Chromium/Playwright binary is available in the environment used to build
  this PR. The design system was built to Lighthouse-friendly practices
  (semantic HTML, no layout-shifting images, minimal JS on the shell,
  `next/font`-free system font stack already in place) but the score itself
  is unverified here; run `npx lighthouse http://localhost:3000 --preset=desktop`
  locally or in CI to confirm before shipping.

## Explicitly out of scope (unchanged by this PR)

FastAPI routes, request/response schemas, Providers, the Director Engine,
the Storyboard Engine, the Quality Engine, the database and its migrations.
Every component introduced here is presentational: it receives data and
callbacks from the same, unmodified `lib/api.ts` functions the product
already used.
