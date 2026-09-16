import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ProductionPlan } from '../api';
import {
  STORYBOARD_HISTORY_LIMIT,
  commitStoryboardState,
  createStoryboardHistory,
  createSceneId,
  createStoryboardState,
  duplicateScene,
  normalizeMood,
  redoStoryboard,
  removeScene,
  reorderScene,
  sanitizeDuration,
  totalDuration,
  undoStoryboard,
  updateCameraPreset,
  updateScene,
  updateSceneMood,
} from './storyboard_state';

const plan = (): ProductionPlan => ({
  id: 'prod_006',
  title: 'Storyboard cinematic editor',
  concept: 'Visual editing over a Director AI production plan',
  mood: 'Minimal',
  audience: 'studio',
  platform: 'web',
  duration: 24,
  style: 'neutral filmic LUT',
  music: 'ambient',
  voice: 'natural',
  persona_id: null,
  created_at: '2026-09-15T00:00:00.000Z',
  shots: [1, 2, 3, 4].map(number => ({
    scene_number: number,
    title: `Cena ${number}`,
    objective: `Objetivo ${number}`,
    emotion: `emoção ${number}`,
    camera: number === 1 ? 'Drone' : 'Static',
    lens: '50mm',
    lighting: 'soft key',
    motion: 'motivated movement',
    duration: number * 2,
    prompt: `prompt ${number}`,
    negative_prompt: 'no incoherent cuts',
    environment: `ambiente ${number}`,
  })),
});

const ids = (...values: string[]) => {
  let index = 0;
  return () => values[index++] ?? `scene-${index}`;
};

const tick = (label: string) => () => `2026-09-15T00:00:${label}.000Z`;

function initialState() {
  return createStoryboardState(plan(), 'project-006', ids('s1', 's2', 's3', 's4'), tick('01'));
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('PR006 StoryboardState', () => {
  it('creates UUIDs through crypto when available and falls back otherwise', () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'uuid-from-crypto' });
    expect(createSceneId()).toBe('uuid-from-crypto');

    vi.stubGlobal('crypto', undefined);
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    expect(createSceneId()).toMatch(/^scene_/);
    vi.mocked(Math.random).mockRestore();
  });

  it('normalizes moods and unsafe durations', () => {
    expect(normalizeMood(' neo ')).toBe('Neo');
    expect(normalizeMood('unknown')).toBe('Minimal');
    expect(sanitizeDuration(Number.NaN)).toBe(0.1);
  });

  it('creates a versioned entity from a ProductionPlan and persists timeline markers', () => {
    const state = initialState();

    expect(state.project_id).toBe('project-006');
    expect(state.production_plan_id).toBe('prod_006');
    expect(state.version).toBe(1);
    expect(state.updated_at).toBe('2026-09-15T00:00:01.000Z');
    expect(state.scenes.map(scene => scene.id)).toEqual(['s1', 's2', 's3', 's4']);
    expect(state.scenes.map(scene => scene.scene_number)).toEqual([1, 2, 3, 4]);
    expect(state.scenes.map(scene => [scene.timeline_start, scene.timeline_end])).toEqual([
      [0, 2],
      [2, 6],
      [6, 12],
      [12, 20],
    ]);
    expect(totalDuration(state)).toBe(20);
  });

  it('updates one scene field without recreating the other scenes', () => {
    const state = initialState();
    const next = updateScene(state, 's2', { title: 'Novo título', objective: 'Novo objetivo' }, tick('02'));

    expect(next.version).toBe(2);
    expect(next.updated_at).toBe('2026-09-15T00:00:02.000Z');
    expect(next.scenes[1]).toMatchObject({ id: 's2', title: 'Novo título', objective: 'Novo objetivo' });
    expect(next.scenes[0]).toBe(state.scenes[0]);
    expect(next.scenes[2]).toBe(state.scenes[2]);
    expect(next.scenes[1].prompt).toBe(state.scenes[1].prompt);
  });

  it('sanitizes duration edits and recomputes total duration', () => {
    const state = initialState();
    const next = updateScene(state, 's1', { duration: 7.456 }, tick('03'));

    expect(next.scenes[0]).toMatchObject({ duration: 7.46, timeline_start: 0, timeline_end: 7.46 });
    expect(next.scenes[1].timeline_start).toBe(7.46);
    expect(totalDuration(next)).toBe(25.46);

    const sanitized = updateScene(next, 's1', { duration: -100 }, tick('04'));
    expect(sanitized.scenes[0].duration).toBe(0.1);
  });

  it('reorders scenes from drag/drop, then updates scene numbers and timeline', () => {
    const state = initialState();
    const next = reorderScene(state, 's4', 's2', tick('05'));

    expect(next.version).toBe(2);
    expect(next.scenes.map(scene => scene.id)).toEqual(['s1', 's4', 's2', 's3']);
    expect(next.scenes.map(scene => scene.scene_number)).toEqual([1, 2, 3, 4]);
    expect(next.scenes.map(scene => scene.timeline_start)).toEqual([0, 2, 10, 14]);
    expect(totalDuration(next)).toBe(totalDuration(state));
  });

  it('ignores no-op storyboard mutations without incrementing version', () => {
    const state = initialState();
    expect(reorderScene(state, 's1', 's1')).toBe(state);
    expect(reorderScene(state, 'missing', 's1')).toBe(state);
    expect(updateScene(state, 'missing', { title: 'No-op' })).toBe(state);
    expect(updateSceneMood(state, 'missing', 'Epic')).toBe(state);
    expect(duplicateScene(state, 'missing')).toBe(state);
    expect(removeScene(state, 'missing')).toBe(state);
  });

  it('updates the CameraDirector slice only when a camera preset is selected', () => {
    const state = initialState();
    const next = updateCameraPreset(state, 's3', 'Hero Walk', tick('06'));

    expect(next.version).toBe(2);
    expect(next.scenes[2]).toMatchObject({
      id: 's3',
      camera: 'Hero Walk',
      lens: '35mm anamorphic',
      lighting: 'motivated hero key with controlled rim light',
    });
    expect(next.scenes[2].motion).toContain('dolly tracking');
    expect(next.scenes[2].objective).toBe(state.scenes[2].objective);
    expect(next.scenes[2].mood).toBe(state.scenes[2].mood);
  });

  it('updates per-scene mood and LUT without touching camera fields', () => {
    const state = initialState();
    const next = updateSceneMood(state, 's2', 'Neo', tick('07'));

    expect(next.version).toBe(2);
    expect(next.scenes[1].mood).toBe('Neo');
    expect(next.scenes[1].lut).toBe('saturated cyan-magenta neo-city LUT');
    expect(next.scenes[1].camera).toBe(state.scenes[1].camera);
    expect(next.scenes[1].lens).toBe(state.scenes[1].lens);
  });

  it('duplicates a scene with a fresh UUID while keeping camera and mood', () => {
    const state = updateSceneMood(initialState(), 's2', 'Luxury', tick('08'));
    const duplicated = duplicateScene(state, 's2', ids('uuid-copy'), tick('09'));

    expect(duplicated.version).toBe(3);
    expect(duplicated.scenes.map(scene => scene.id)).toEqual(['s1', 's2', 'uuid-copy', 's3', 's4']);
    expect(duplicated.scenes[2]).toMatchObject({
      id: 'uuid-copy',
      camera: state.scenes[1].camera,
      mood: 'Luxury',
      lut: state.scenes[1].lut,
    });
    expect(duplicated.scenes.map(scene => scene.scene_number)).toEqual([1, 2, 3, 4, 5]);
  });

  it('removes a scene and persists the renumbered storyboard state', () => {
    const state = initialState();
    const next = removeScene(state, 's1', tick('10'));

    expect(next.version).toBe(2);
    expect(next.scenes.map(scene => scene.id)).toEqual(['s2', 's3', 's4']);
    expect(next.scenes.map(scene => scene.scene_number)).toEqual([1, 2, 3]);
    expect(next.scenes[0].timeline_start).toBe(0);
  });

  it('does not remove the final scene', () => {
    const oneScene = {
      ...initialState(),
      scenes: [initialState().scenes[0]],
    };
    expect(removeScene(oneScene, 's1')).toBe(oneScene);
  });

  it('undoes and redoes edit, reorder, duplicate and remove operations', () => {
    const state = initialState();
    let history = createStoryboardHistory(state);
    history = commitStoryboardState(history, updateScene(history.present, 's1', { title: 'Editada' }, tick('11')));
    history = commitStoryboardState(history, reorderScene(history.present, 's4', 's2', tick('12')));
    history = commitStoryboardState(history, duplicateScene(history.present, 's4', ids('s4-copy'), tick('13')));
    history = commitStoryboardState(history, removeScene(history.present, 's1', tick('14')));

    expect(history.present.version).toBe(5);
    history = undoStoryboard(history);
    expect(history.present.scenes.map(scene => scene.id)).toContain('s1');
    history = undoStoryboard(history);
    expect(history.present.scenes.map(scene => scene.id)).not.toContain('s4-copy');
    history = redoStoryboard(history);
    expect(history.present.scenes.map(scene => scene.id)).toContain('s4-copy');
    history = redoStoryboard(history);
    expect(history.present.scenes.map(scene => scene.id)).not.toContain('s1');
  });

  it('keeps a maximum of 50 historical states and ignores empty history moves', () => {
    let history = createStoryboardHistory(initialState(), STORYBOARD_HISTORY_LIMIT);
    expect(commitStoryboardState(history, { ...history.present })).toBe(history);
    expect(undoStoryboard(history)).toBe(history);
    expect(redoStoryboard(history)).toBe(history);

    for (let index = 0; index < STORYBOARD_HISTORY_LIMIT + 5; index += 1) {
      history = commitStoryboardState(
        history,
        updateScene(history.present, 's1', { title: `Edit ${index}` }, () => `t-${index}`),
      );
    }

    expect(history.past).toHaveLength(STORYBOARD_HISTORY_LIMIT);
    expect(history.present.version).toBe(STORYBOARD_HISTORY_LIMIT + 6);
  });
});
