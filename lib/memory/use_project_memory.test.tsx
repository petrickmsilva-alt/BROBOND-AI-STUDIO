// @vitest-environment jsdom
//
// PR004.1 — the hook only consumes the adapter: it exposes { memory, save,
// clear }, performs partial updates, and never touches storage itself.

import { renderHook, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { useProjectMemory } from './use_project_memory';
import { PROJECT_ID, loadProjectMemory, saveProjectMemory } from './project_memory';

const PROJECT = 'test-project';

function preSave(state: Record<string, unknown> = {}) {
  saveProjectMemory({ projectId: PROJECT, ...state });
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  window.localStorage.clear();
});

describe('useProjectMemory', () => {
  it('loads the stored memory on mount (synchronously)', () => {
    preSave({ personaId: 'p-1', styleId: 'cinematic noir' });
    const { result } = renderHook(() => useProjectMemory(PROJECT));
    expect(result.current.memory?.personaId).toBe('p-1');
    expect(result.current.memory?.styleId).toBe('cinematic noir');
  });

  it('starts null when the project has no memory', () => {
    const { result } = renderHook(() => useProjectMemory(PROJECT));
    expect(result.current.memory).toBeNull();
  });

  it('save performs a partial update: merges and persists', () => {
    preSave({ personaId: 'p-1', styleId: 'cinematic noir', loraId: 'lora-1' });
    const { result } = renderHook(() => useProjectMemory(PROJECT));

    act(() => {
      result.current.save({ loraId: 'lora-2' });
    });

    // In-memory state merged, not replaced.
    expect(result.current.memory?.personaId).toBe('p-1');
    expect(result.current.memory?.styleId).toBe('cinematic noir');
    expect(result.current.memory?.loraId).toBe('lora-2');
    expect(result.current.memory?.projectId).toBe(PROJECT);
    expect(result.current.memory?.updatedAt).toBeTruthy();

    // And the adapter persisted the merged state.
    const stored = loadProjectMemory(PROJECT);
    expect(stored?.loraId).toBe('lora-2');
    expect(stored?.personaId).toBe('p-1');
  });

  it('save works from an empty memory (first save creates the state)', () => {
    const { result } = renderHook(() => useProjectMemory(PROJECT));
    act(() => {
      result.current.save({ personaId: 'p-9' });
    });
    expect(result.current.memory?.personaId).toBe('p-9');
    expect(result.current.memory?.projectId).toBe(PROJECT);
    expect(loadProjectMemory(PROJECT)?.personaId).toBe('p-9');
  });

  it('save always enforces the hook project id (patch cannot retarget)', () => {
    const { result } = renderHook(() => useProjectMemory(PROJECT));
    act(() => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      result.current.save({ projectId: 'hijack', personaId: 'p-1' } as any);
    });
    expect(result.current.memory?.projectId).toBe(PROJECT);
    expect(loadProjectMemory(PROJECT)?.personaId).toBe('p-1');
    expect(loadProjectMemory('hijack')).toBeNull();
  });

  it('clear removes the memory (state and storage)', () => {
    preSave({ personaId: 'p-1' });
    const { result } = renderHook(() => useProjectMemory(PROJECT));
    expect(result.current.memory).not.toBeNull();

    act(() => {
      result.current.clear();
    });

    expect(result.current.memory).toBeNull();
    expect(loadProjectMemory(PROJECT)).toBeNull();
  });

  it('is stable across renders for the same project id', () => {
    const { result, rerender } = renderHook(({ id }: { id: string }) => useProjectMemory(id), {
      initialProps: { id: PROJECT_ID },
    });
    const first = result.current;
    rerender({ id: PROJECT_ID });
    expect(result.current.save).toBe(first.save);
    expect(result.current.clear).toBe(first.clear);
  });
});
