// PR004.1 — Project Memory contract: adapter behavioral tests.
//
// Covers the spec's list: persistence, serialization, deserialization,
// partial update, clear and version compatibility — plus the storage seam
// (SSR / blocked storage) and the auth-token accessors that ride on it.

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  AUTH_TOKEN_KEY,
  LEGACY_PERSONA_ID_KEY,
  PROJECT_ID,
  PROJECT_MEMORY_KEY,
  PROJECT_MEMORY_VERSION,
  browserStorage,
  clearAuthToken,
  clearProjectMemory,
  getAuthToken,
  loadProjectMemory,
  saveProjectMemory,
  setAuthToken,
  setLegacyPersonaId,
  type ProjectMemoryState,
} from './project_memory';

// ---------------------------------------------------------------------------
// Browser harness: a fake window.localStorage, swapped in per test.
// ---------------------------------------------------------------------------

interface FakeStorage {
  storage: Storage;
  raw: Map<string, string>;
}

function makeLocalStorage(): FakeStorage {
  const raw = new Map<string, string>();
  const storage = {
    getItem: (key: string) => (raw.has(key) ? raw.get(key)! : null),
    setItem: (key: string, value: string) => void raw.set(key, String(value)),
    removeItem: (key: string) => void raw.delete(key),
    clear: () => void raw.clear(),
    key: (index: number) => [...raw.keys()][index] ?? null,
    get length() {
      return raw.size;
    },
  } as unknown as Storage;
  return { storage, raw };
}

let raw: Map<string, string>;

beforeEach(() => {
  const fake = makeLocalStorage();
  raw = fake.raw;
  (globalThis as Record<string, unknown>).window = { localStorage: fake.storage };
});

afterEach(() => {
  delete (globalThis as Record<string, unknown>).window;
});

function fullState(overrides: Partial<ProjectMemoryState> = {}): ProjectMemoryState {
  return {
    projectId: PROJECT_ID,
    workspaceId: 'ws-1',
    personaId: 'persona-1',
    wardrobeId: 'leather jacket, red dress',
    styleId: 'cinematic noir',
    loraId: 'lora-1',
    cameraPreset: 'tracking',
    aspectRatio: '9:16',
    lastPrompt: 'a directed frame',
    lastPlatform: 'video',
    duration: 10,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Persistence
// ---------------------------------------------------------------------------

describe('persistence', () => {
  it('round-trips a full state through the single official key', () => {
    const state = fullState();
    saveProjectMemory(state);

    // Exactly one key, and it is the official one.
    expect([...raw.keys()]).toEqual([PROJECT_MEMORY_KEY]);

    const loaded = loadProjectMemory(PROJECT_ID);
    expect(loaded).not.toBeNull();
    expect(loaded).toMatchObject(state);
    expect(loaded?.projectId).toBe(PROJECT_ID);
  });

  it('isolates projects: saving/clearing one never touches the other', () => {
    saveProjectMemory(fullState({ projectId: 'proj-a', personaId: 'p-a' }));
    saveProjectMemory(fullState({ projectId: 'proj-b', personaId: 'p-b' }));

    expect(loadProjectMemory('proj-a')?.personaId).toBe('p-a');
    expect(loadProjectMemory('proj-b')?.personaId).toBe('p-b');

    clearProjectMemory('proj-a');
    expect(loadProjectMemory('proj-a')).toBeNull();
    expect(loadProjectMemory('proj-b')?.personaId).toBe('p-b');
  });

  it('returns null for a project that was never saved', () => {
    saveProjectMemory(fullState());
    expect(loadProjectMemory('never-saved')).toBeNull();
  });

  it('is a no-op outside a browser (SSR) — never throws', () => {
    delete (globalThis as Record<string, unknown>).window;
    expect(browserStorage()).toBeNull();
    expect(loadProjectMemory(PROJECT_ID)).toBeNull();
    expect(() => saveProjectMemory(fullState())).not.toThrow();
    expect(() => clearProjectMemory(PROJECT_ID)).not.toThrow();
  });

  it('degrades to null when the storage itself is unavailable', () => {
    const throwing = {
      get localStorage() {
        throw new Error('blocked');
      },
    };
    (globalThis as Record<string, unknown>).window = throwing;
    expect(browserStorage()).toBeNull();
    expect(loadProjectMemory(PROJECT_ID)).toBeNull();
    expect(() => saveProjectMemory(fullState())).not.toThrow();
  });

  it('degrades gracefully when the storage methods throw (hostile storage)', () => {
    // A browser that allows access but fails on every operation (quota,
    // privacy enforcement mid-session): nothing may throw.
    const hostile = {
      getItem: () => {
        throw new Error('quota');
      },
      setItem: () => {
        throw new Error('quota');
      },
      removeItem: () => {
        throw new Error('quota');
      },
    } as unknown as Storage;
    (globalThis as Record<string, unknown>).window = { localStorage: hostile };

    expect(loadProjectMemory(PROJECT_ID)).toBeNull();
    expect(() => saveProjectMemory(fullState())).not.toThrow();
    expect(() => clearProjectMemory(PROJECT_ID)).not.toThrow();
    expect(getAuthToken()).toBeNull();
    expect(() => setAuthToken('x')).not.toThrow();
    expect(() => clearAuthToken()).not.toThrow();
    expect(() => setLegacyPersonaId('p')).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Serialization
// ---------------------------------------------------------------------------

describe('serialization', () => {
  it('stores the versioned envelope under the single key', () => {
    saveProjectMemory(fullState({ projectId: 'proj-x' }));
    const envelope = JSON.parse(raw.get(PROJECT_MEMORY_KEY)!) as {
      v: number;
      projects: Record<string, ProjectMemoryState>;
    };
    expect(envelope.v).toBe(PROJECT_MEMORY_VERSION);
    expect(Object.keys(envelope.projects)).toEqual(['proj-x']);
  });

  it('stamps updatedAt (a valid ISO timestamp) on every save', () => {
    const before = Date.now();
    const stored = saveProjectMemory(fullState());
    const after = Date.now();
    const stamped = new Date(stored.updatedAt!).getTime();
    expect(Number.isNaN(stamped)).toBe(false);
    expect(stamped).toBeGreaterThanOrEqual(before);
    expect(stamped).toBeLessThanOrEqual(after);
  });

  it('returns the stored state so callers can chain', () => {
    const state = fullState();
    const stored = saveProjectMemory(state);
    expect(stored).toMatchObject(state);
    expect(loadProjectMemory(PROJECT_ID)).toMatchObject(stored);
  });
});

// ---------------------------------------------------------------------------
// Deserialization
// ---------------------------------------------------------------------------

describe('deserialization', () => {
  it('coerces and sanitizes: keeps valid fields, drops wrong types', () => {
    const document = {
      v: PROJECT_MEMORY_VERSION,
      projects: {
        'proj-dirty': {
          projectId: 'proj-dirty',
          personaId: 'persona-1',
          personaName: 'should be dropped',
          duration: '10', // string, not number -> dropped
          cameraPreset: '', // empty string -> dropped
          aspectRatio: '1:1',
          unknownFutureField: 42,
        },
      },
    };
    raw.set(PROJECT_MEMORY_KEY, JSON.stringify(document));

    const loaded = loadProjectMemory('proj-dirty');
    expect(loaded).not.toBeNull();
    expect(loaded?.personaId).toBe('persona-1');
    expect(loaded?.aspectRatio).toBe('1:1');
    expect(loaded?.duration).toBeUndefined();
    expect(loaded?.cameraPreset).toBeUndefined();
    expect('personaName' in (loaded as object)).toBe(false);
    expect('unknownFutureField' in (loaded as object)).toBe(false);
  });

  it('returns null for corrupt JSON (degraded memory, never a crash)', () => {
    raw.set(PROJECT_MEMORY_KEY, '{not json');
    expect(loadProjectMemory(PROJECT_ID)).toBeNull();
  });

  it('returns null when the stored value is not an object', () => {
    raw.set(PROJECT_MEMORY_KEY, '42');
    expect(loadProjectMemory(PROJECT_ID)).toBeNull();
  });

  it('drops non-object entries inside the projects map', () => {
    raw.set(
      PROJECT_MEMORY_KEY,
      JSON.stringify({
        v: PROJECT_MEMORY_VERSION,
        projects: { 'proj-str': 'not-an-object', 'proj-ok': { projectId: 'proj-ok' } },
      }),
    );
    expect(loadProjectMemory('proj-str')).toBeNull();
    expect(loadProjectMemory('proj-ok')).not.toBeNull();
  });

  it('returns null for an empty store (key missing)', () => {
    expect(loadProjectMemory(PROJECT_ID)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Partial update (adapter level)
// ---------------------------------------------------------------------------

describe('partial update', () => {
  it('a save carrying a subset keeps everything the caller preserves', () => {
    const original = fullState();
    saveProjectMemory(original);

    // The hook is what merges; the adapter stores what it is given. A
    // caller that re-saves the merged state must not lose fields.
    const merged = { ...original, loraId: 'lora-2' };
    saveProjectMemory(merged);

    const loaded = loadProjectMemory(PROJECT_ID);
    expect(loaded?.loraId).toBe('lora-2');
    expect(loaded?.personaId).toBe(original.personaId);
    expect(loaded?.wardrobeId).toBe(original.wardrobeId);
    expect(loaded?.duration).toBe(original.duration);
  });
});

// ---------------------------------------------------------------------------
// Clear
// ---------------------------------------------------------------------------

describe('clear', () => {
  it('removes only the addressed project', () => {
    saveProjectMemory(fullState({ projectId: 'keep-me' }));
    saveProjectMemory(fullState({ projectId: 'drop-me' }));

    clearProjectMemory('drop-me');
    expect(loadProjectMemory('drop-me')).toBeNull();
    expect(loadProjectMemory('keep-me')).not.toBeNull();
  });

  it('is a no-op for an unknown project or an empty store', () => {
    expect(() => clearProjectMemory('ghost')).not.toThrow();
    saveProjectMemory(fullState());
    expect(() => clearProjectMemory('ghost-2')).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Version compatibility
// ---------------------------------------------------------------------------

describe('version compatibility', () => {
  it('migrates the v0 (PR004) flat shape once, into the v1 envelope', () => {
    raw.set(
      PROJECT_MEMORY_KEY,
      JSON.stringify({
        persona_id: 'persona-legacy',
        default_style: 'cinematic realism',
        last_lora: 'lora-legacy',
        selected_wardrobe: ['jacket', 'hat'],
      }),
    );

    const loaded = loadProjectMemory(PROJECT_ID);
    expect(loaded?.personaId).toBe('persona-legacy');
    expect(loaded?.styleId).toBe('cinematic realism');
    expect(loaded?.loraId).toBe('lora-legacy');
    // Canonical join is the compact `,` — readers split on `,` (the backend
    // additionally strips, so human-written `, ` also parses).
    expect(loaded?.wardrobeId).toBe('jacket,hat');

    // The migration is write-through: the stored document is now v1.
    const envelope = JSON.parse(raw.get(PROJECT_MEMORY_KEY)!) as { v: number };
    expect(envelope.v).toBe(PROJECT_MEMORY_VERSION);
  });

  it('ignores a v0 document that does not look like the legacy shape', () => {
    raw.set(PROJECT_MEMORY_KEY, JSON.stringify({ something: 'else' }));
    expect(loadProjectMemory(PROJECT_ID)).toBeNull();
  });

  it('migrates a partial v0 document (missing/malformed optional fields)', () => {
    raw.set(PROJECT_MEMORY_KEY, JSON.stringify({ persona_id: 'p-only' }));
    const loaded = loadProjectMemory(PROJECT_ID);
    expect(loaded?.personaId).toBe('p-only');
    expect(loaded?.loraId).toBeUndefined();
    expect(loaded?.styleId).toBeUndefined();
    expect(loaded?.wardrobeId).toBeUndefined();

    // A v0 doc whose selected_wardrobe is not an array: migrated without a
    // wardrobe, still a valid v1 document.
    raw.set(
      PROJECT_MEMORY_KEY,
      JSON.stringify({ persona_id: 'p-2', selected_wardrobe: 'jacket' }),
    );
    const loaded2 = loadProjectMemory(PROJECT_ID);
    expect(loaded2?.personaId).toBe('p-2');
    expect(loaded2?.wardrobeId).toBeUndefined();
  });

  it('refuses an unknown future version instead of guessing (raw untouched)', () => {
    const future = { v: 99, projects: { [PROJECT_ID]: fullState() } };
    raw.set(PROJECT_MEMORY_KEY, JSON.stringify(future));

    expect(loadProjectMemory(PROJECT_ID)).toBeNull();
    // No silent data loss: the raw document is exactly what was written.
    expect(raw.get(PROJECT_MEMORY_KEY)).toBe(JSON.stringify(future));
  });

  it('always guarantees the required projectId on loaded state', () => {
    const document = {
      v: PROJECT_MEMORY_VERSION,
      projects: { 'proj-noid': { personaId: 'p' } }, // projectId missing
    };
    raw.set(PROJECT_MEMORY_KEY, JSON.stringify(document));
    const loaded = loadProjectMemory('proj-noid');
    expect(loaded?.projectId).toBe('proj-noid');
  });
});

// ---------------------------------------------------------------------------
// Storage seam: auth token + legacy persona id
// ---------------------------------------------------------------------------

describe('storage seam (auth token / legacy persona)', () => {
  it('auth token round-trips through the named accessors only', () => {
    expect(getAuthToken()).toBeNull();
    setAuthToken('token-123');
    expect(getAuthToken()).toBe('token-123');
    expect(raw.get(AUTH_TOKEN_KEY)).toBe('token-123');
    clearAuthToken();
    expect(getAuthToken()).toBeNull();
  });

  it('setAuthToken is a no-op for an empty token (never overwrites)', () => {
    setAuthToken('real');
    setAuthToken('');
    expect(getAuthToken()).toBe('real');
  });

  it('legacy persona id is written through its named accessor', () => {
    setLegacyPersonaId('persona-legacy');
    expect(raw.get(LEGACY_PERSONA_ID_KEY)).toBe('persona-legacy');
  });

  it('accessors are SSR-safe', () => {
    delete (globalThis as Record<string, unknown>).window;
    expect(getAuthToken()).toBeNull();
    expect(() => setAuthToken('x')).not.toThrow();
    expect(() => clearAuthToken()).not.toThrow();
    expect(() => setLegacyPersonaId('p')).not.toThrow();
  });
});
