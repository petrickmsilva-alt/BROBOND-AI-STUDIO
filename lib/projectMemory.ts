// PR004 (ETAPA 6) — Project Memory.
//
// Each project in the studio persists the creative state that makes the next
// session continuous: which persona is the identity, which style was in use,
// the last LoRA version chosen, and the wardrobe items selected.
//
// Where does it live? The database has no project-state column — and the PR
// explicitly forbids structural changes ("apenas entidades existentes") — so
// the memory is persisted in the browser (localStorage), keyed per project.
// The shape mirrors the backend field names (`persona_id`, `default_style`,
// `last_lora`, `selected_wardrobe`), so a future server-side project entity
// can adopt the same payload 1:1 without a client migration.

export interface ProjectMemory {
  persona_id: string | null;
  default_style: string;
  last_lora: string;
  selected_wardrobe: string[];
}

const STORAGE_KEY = 'brobond_project_memory';

/**
 * The studio keeps a single active project per browser workspace (the
 * product has no multi-project switching yet; "Projects" in the sidebar is
 * the assets library). The id is stable so the memory survives reloads.
 */
export const PROJECT_ID = 'brobond-project-01';

export const emptyProjectMemory: ProjectMemory = {
  persona_id: null,
  default_style: '',
  last_lora: '',
  selected_wardrobe: [],
};

/**
 * Restore the project's saved state. Corrupt or missing storage degrades to
 * the empty memory — a broken localStorage must never break the studio.
 */
export function loadProjectMemory(): ProjectMemory {
  if (typeof window === 'undefined') return { ...emptyProjectMemory };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...emptyProjectMemory };
    const parsed = JSON.parse(raw) as Partial<ProjectMemory>;
    return {
      persona_id: typeof parsed.persona_id === 'string' && parsed.persona_id ? parsed.persona_id : null,
      default_style: typeof parsed.default_style === 'string' ? parsed.default_style : '',
      last_lora: typeof parsed.last_lora === 'string' ? parsed.last_lora : '',
      selected_wardrobe: Array.isArray(parsed.selected_wardrobe) ? parsed.selected_wardrobe.map(String) : [],
    };
  } catch {
    return { ...emptyProjectMemory };
  }
}

/** Persist the project's creative state. Best effort: never throws. */
export function saveProjectMemory(memory: ProjectMemory): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(memory));
  } catch {
    // Storage full or blocked: the session continues without memory.
  }
}
