// LEGACY (PR004) — Project Memory v0. Marked Legacy per Developer Bible §2:
// never deleted, only marked.
//
// Since PR004.1 there are NO live call sites — the official contract and the
// only storage boundary live in `lib/memory/project_memory.ts` (the Memory
// Adapter), consumed by `lib/memory/use_project_memory.ts`. This file is kept
// so any old import keeps resolving, and it MUST NOT touch
// `window.localStorage` directly (that is the adapter's job, enforced by
// `test_project_memory_contract.py`).
//
// The v0 shape is mapped onto the official `ProjectMemoryState`:
//   persona_id -> personaId      default_style -> styleId
//   last_lora  -> loraId         selected_wardrobe -> wardrobeId (joined)
// What has no contract home (none, today) simply stops being read back.

import {
  loadProjectMemory as loadState,
  saveProjectMemory as saveState,
  PROJECT_ID,
} from './memory/project_memory';

export interface ProjectMemory {
  persona_id: string | null;
  default_style: string;
  last_lora: string;
  selected_wardrobe: string[];
}

/** Stable project id — re-exported from the adapter (single source). */
export const PROJECT_MEMORY_ID = PROJECT_ID;

export const emptyProjectMemory: ProjectMemory = {
  persona_id: null,
  default_style: '',
  last_lora: '',
  selected_wardrobe: [],
};

export function loadProjectMemory(): ProjectMemory {
  const state = loadState(PROJECT_ID);
  return {
    persona_id: state?.personaId ?? null,
    default_style: state?.styleId ?? '',
    last_lora: state?.loraId ?? '',
    selected_wardrobe: state?.wardrobeId ? state.wardrobeId.split(',') : [],
  };
}

export function saveProjectMemory(memory: ProjectMemory): void {
  saveState({
    projectId: PROJECT_ID,
    personaId: memory.persona_id ?? null,
    styleId: memory.default_style || null,
    loraId: memory.last_lora || null,
    wardrobeId: memory.selected_wardrobe.length ? memory.selected_wardrobe.join(',') : null,
  });
}
