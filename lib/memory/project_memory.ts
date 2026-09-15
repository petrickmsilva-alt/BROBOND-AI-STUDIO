// PR004.1 — Project Memory: the official contract and the Memory Adapter.
//
// This module is the ONLY place in the codebase that may touch
// `window.localStorage` (enforced by `test_project_memory_contract.py`).
// Components and other modules never see the storage key — they know only:
//
//   loadProjectMemory(projectId)
//   saveProjectMemory(state)
//   clearProjectMemory(projectId)
//
// The same three signatures (and the same `ProjectMemoryState` object) will
// be served by the future PostgreSQL-backed implementation; the client must
// not change. See docs/PROJECT_MEMORY.md.
//
// Storage layout (browser, today):
//
//   PROJECT_MEMORY_KEY -> {
//     "v": 1,                                  // envelope version (migration)
//     "projects": { "<projectId>": ProjectMemoryState, ... }
//   }
//
// One official key, many projects. The per-project state object — and only
// that object — is the contract shared with the future server-side store.

export interface ProjectMemoryState {
  /** The only required field: which project this state belongs to. */
  projectId: string;
  /** Workspace tenant the project belongs to (known when a persona is set). */
  workspaceId?: string | null;
  /** The active persona (PR003 profile id). */
  personaId?: string | null;
  /** Wardrobe selection. Today: the selected item names, comma joined (the
   * studio has no per-item ids yet); future: the wardrobe entry id. */
  wardrobeId?: string | null;
  /** The style in use. Today: the style name; future: the style id. */
  styleId?: string | null;
  /** The last LoRA version chosen (asset id). */
  loraId?: string | null;
  /** The camera preset of the video studio (static/pan/tilt/zoom/tracking/crane). */
  cameraPreset?: string | null;
  /** The aspect ratio in use (16:9 / 9:16 / 1:1). */
  aspectRatio?: string | null;
  /** The last prompt text (restored into the studio textarea). */
  lastPrompt?: string | null;
  /** The last platform used ('image' | 'video'). */
  lastPlatform?: string | null;
  /** The video duration in seconds (5 | 10 | 15). */
  duration?: number | null;
  /** ISO timestamp of the last save (stamped by `saveProjectMemory`). */
  updatedAt?: string | null;
}

/** Envelope version. The contract never changes without a migration: a new
 *  version means new code here, never a client rewrite. */
export const PROJECT_MEMORY_VERSION = 1;

/** The single official storage key. Nothing else in the app may hard-code a
 *  project-memory key. */
export const PROJECT_MEMORY_KEY = 'brobond_project_memory';

/** The studio's single active project (the product has no multi-project
 *  switching yet — "Projects" in the sidebar is the assets library). */
export const PROJECT_ID = 'brobond-project-01';

/**
 * Auth-token seam (PR002's token, kept for compatibility).
 *
 * This is NOT part of `ProjectMemoryState` — it is the login session token.
 * It lives here for one reason only: the adapter is the single storage
 * boundary of the frontend, so no component (or `lib`) may name the raw key
 * or touch `window.localStorage` itself. The guard in
 * `test_project_memory_contract.py` enforces that invariant.
 */
export const AUTH_TOKEN_KEY = 'brobond_access_token';

export function getAuthToken(): string | null {
  const storage = browserStorage();
  if (!storage) return null;
  try {
    const value = storage.getItem(AUTH_TOKEN_KEY);
    return value && value.length > 0 ? value : null;
  } catch {
    return null;
  }
}

export function setAuthToken(token: string): void {
  const storage = browserStorage();
  if (!storage || !token) return;
  try {
    storage.setItem(AUTH_TOKEN_KEY, token);
  } catch {
    // Best effort: a blocked storage must never break a successful login.
  }
}

export function clearAuthToken(): void {
  const storage = browserStorage();
  if (!storage) return;
  try {
    storage.removeItem(AUTH_TOKEN_KEY);
  } catch {
    // Best effort.
  }
}

/**
 * LEGACY (pre-PR004) — the Persona Lab writes the persona id it trains so
 * the studios can preload its LoRA versions. Superseded by Project Memory
 * (`personaId`), kept because Legacy is never deleted (Bible §2). Written
 * through a named accessor so no component names the raw key.
 */
export const LEGACY_PERSONA_ID_KEY = 'brobond_persona_id';

export function setLegacyPersonaId(personaId: string): void {
  const storage = browserStorage();
  if (!storage || !personaId) return;
  try {
    storage.setItem(LEGACY_PERSONA_ID_KEY, personaId);
  } catch {
    // Best effort.
  }
}

interface ProjectMemoryStore {
  v: number;
  projects: Record<string, ProjectMemoryState>;
}

// ---------------------------------------------------------------------------
// Browser storage seam
// ---------------------------------------------------------------------------

/**
 * The raw seam: the ONLY function in the repository that reads
 * `window.localStorage`. Returns `null` outside a browser (SSR) or when
 * storage is unavailable (private mode) — every consumer treats `null` as
 * "memory disabled", never as an error.
 *
 * The auth-token flow (PR002) also uses this seam with its own key; the
 * token is a separate contract and is NOT part of `ProjectMemoryState`.
 */
export function browserStorage(): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Serialization (the only place the state shape is known)
// ---------------------------------------------------------------------------

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

function asDuration(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null;
}

/**
 * Coerce an unknown document into the contract. Unknown fields are dropped
 * (forward compatibility: a newer field on disk must not leak into the
 * client), wrong types become `null`/absent. Returns `null` when the
 * document is not even an object.
 */
function sanitizeState(raw: unknown, fallbackProjectId: string): ProjectMemoryState | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const doc = raw as Record<string, unknown>;
  const state: ProjectMemoryState = {
    projectId: asString(doc.projectId) ?? fallbackProjectId,
  };
  const workspaceId = asString(doc.workspaceId);
  if (workspaceId) state.workspaceId = workspaceId;
  const personaId = asString(doc.personaId);
  if (personaId) state.personaId = personaId;
  const wardrobeId = asString(doc.wardrobeId);
  if (wardrobeId) state.wardrobeId = wardrobeId;
  const styleId = asString(doc.styleId);
  if (styleId) state.styleId = styleId;
  const loraId = asString(doc.loraId);
  if (loraId) state.loraId = loraId;
  const cameraPreset = asString(doc.cameraPreset);
  if (cameraPreset) state.cameraPreset = cameraPreset;
  const aspectRatio = asString(doc.aspectRatio);
  if (aspectRatio) state.aspectRatio = aspectRatio;
  const lastPrompt = asString(doc.lastPrompt);
  if (lastPrompt) state.lastPrompt = lastPrompt;
  const lastPlatform = asString(doc.lastPlatform);
  if (lastPlatform) state.lastPlatform = lastPlatform;
  const duration = asDuration(doc.duration);
  if (duration !== null) state.duration = duration;
  const updatedAt = asString(doc.updatedAt);
  if (updatedAt) state.updatedAt = updatedAt;
  return state;
}

// ---------------------------------------------------------------------------
// Migration
// ---------------------------------------------------------------------------

const LEGACY_V0_KEYS = ['persona_id', 'default_style', 'last_lora', 'selected_wardrobe'];

/**
 * v0 -> v1 (PR004's flat shape, stored without an envelope). Mappable fields
 * are carried over; what has no contract home is dropped honestly. Runs once:
 * the migrated envelope is written back, so the next read is a plain v1 hit.
 */
function migrateV0(doc: Record<string, unknown>): ProjectMemoryStore {
  const state: ProjectMemoryState = { projectId: PROJECT_ID };
  const personaId = asString(doc.persona_id);
  if (personaId) state.personaId = personaId;
  const lastLora = asString(doc.last_lora);
  if (lastLora) state.loraId = lastLora;
  const defaultStyle = asString(doc.default_style);
  if (defaultStyle) state.styleId = defaultStyle;
  const wardrobe = Array.isArray(doc.selected_wardrobe)
    ? (doc.selected_wardrobe as unknown[]).filter((item): item is string => typeof item === 'string').join(',')
    : '';
  if (wardrobe) state.wardrobeId = wardrobe;
  return { v: PROJECT_MEMORY_VERSION, projects: { [PROJECT_ID]: state } };
}

// ---------------------------------------------------------------------------
// Store read/write
// ---------------------------------------------------------------------------

function writeStore(store: ProjectMemoryStore): void {
  const storage = browserStorage();
  if (!storage) return;
  try {
    storage.setItem(PROJECT_MEMORY_KEY, JSON.stringify(store));
  } catch {
    // Best effort: a full/blocked storage must never break the studio.
  }
}

function readStore(): ProjectMemoryStore | null {
  const storage = browserStorage();
  if (!storage) return null;
  let rawText: string | null = null;
  try {
    rawText = storage.getItem(PROJECT_MEMORY_KEY);
  } catch {
    return null;
  }
  if (!rawText) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(rawText);
  } catch {
    return null; // corrupt JSON: degraded memory, never a crash
  }
  if (typeof parsed !== 'object' || parsed === null) return null;
  const doc = parsed as Record<string, unknown>;
  const v = typeof doc.v === 'number' ? doc.v : 0;

  if (v === 0) {
    const isV0 = LEGACY_V0_KEYS.some(key => key in doc);
    if (!isV0) return null; // unknown legacy shape: do not guess
    const migrated = migrateV0(doc);
    writeStore(migrated);
    return migrated;
  }

  if (v !== PROJECT_MEMORY_VERSION) {
    // Unknown future version: refuse to read (no silent data loss, no
    // guesswork). This is the single, documented migration point.
    return null;
  }

  const projects: Record<string, ProjectMemoryState> = {};
  if (typeof doc.projects === 'object' && doc.projects !== null) {
    for (const [projectId, value] of Object.entries(doc.projects as Record<string, unknown>)) {
      const state = sanitizeState(value, projectId);
      if (state) projects[projectId] = state;
    }
  }
  return { v, projects };
}

// ---------------------------------------------------------------------------
// The Memory Adapter (the public contract — stable across backends)
// ---------------------------------------------------------------------------

/**
 * Load one project's memory. Returns `null` when there is no memory for the
 * project, there is no browser storage, or the stored version is unknown.
 */
export function loadProjectMemory(projectId: string): ProjectMemoryState | null {
  const store = readStore();
  if (!store) return null;
  const state = store.projects[projectId];
  return state ? { ...state, projectId } : null;
}

/**
 * Persist one project's memory (full state; partial updates are the caller's
 * concern — the hook merges). Stamps `updatedAt` and returns the stored
 * state.
 */
export function saveProjectMemory(state: ProjectMemoryState): ProjectMemoryState {
  const store = readStore() ?? { v: PROJECT_MEMORY_VERSION, projects: {} };
  const stamped: ProjectMemoryState = {
    ...state,
    projectId: state.projectId,
    updatedAt: new Date().toISOString(),
  };
  store.projects[stamped.projectId] = stamped;
  writeStore(store);
  return stamped;
}

/**
 * Remove one project's memory. No-op when the project (or storage) does not
 * exist. Other projects are untouched.
 */
export function clearProjectMemory(projectId: string): void {
  const store = readStore();
  if (!store) return;
  if (!(projectId in store.projects)) return;
  delete store.projects[projectId];
  writeStore(store);
}
