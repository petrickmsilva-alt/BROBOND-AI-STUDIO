'use client';

// PR004.1 — the React face of the Project Memory adapter.
//
// The hook ONLY consumes the adapter (`./project_memory`): it never touches
// storage, never knows the key, and never serializes the state itself.
// `save` performs a partial update (shallow merge over the current state);
// `clear` removes the project's memory.

import { useCallback, useState } from 'react';
import {
  clearProjectMemory as clearStoredProject,
  loadProjectMemory,
  saveProjectMemory,
  type ProjectMemoryState,
} from './project_memory';

export type ProjectMemoryHook = {
  /** The loaded memory (`null` while empty/unavailable). */
  memory: ProjectMemoryState | null;
  /** Partial update: merges over the current state and persists. */
  save: (patch: Partial<ProjectMemoryState>) => void;
  /** Remove this project's memory. */
  clear: () => void;
};

export function useProjectMemory(projectId: string): ProjectMemoryHook {
  // Synchronous on purpose: localStorage reads are sync, so the first render
  // already sees the restored state — no effect, no race with the first save.
  const [memory, setMemory] = useState<ProjectMemoryState | null>(() => loadProjectMemory(projectId));

  const save = useCallback((patch: Partial<ProjectMemoryState>) => {
    setMemory(current => {
      const next = {
        ...current,
        ...patch,
        projectId,
        updatedAt: new Date().toISOString(),
      } as ProjectMemoryState;
      saveProjectMemory(next);
      return next;
    });
  }, [projectId]);

  const clear = useCallback(() => {
    clearStoredProject(projectId);
    setMemory(null);
  }, [projectId]);

  return { memory, save, clear };
}
