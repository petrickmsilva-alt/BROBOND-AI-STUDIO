import type { DirectorShotPlan, ProductionPlan } from '../api';

export const FIRST_SCENE_NUMBER = 1;
export const INITIAL_STORYBOARD_VERSION = 1;
export const STORYBOARD_HISTORY_LIMIT = 50;
export const MIN_SCENE_DURATION = 0.1;
export const TIMELINE_PRECISION = 2;

export const moodOptions = ['Luxury', 'Epic', 'Dark', 'Minimal', 'Sport', 'Neo'] as const;
export type SceneMood = (typeof moodOptions)[number];

export const MOOD_LUTS: Record<SceneMood, string> = {
  Luxury: 'clean champagne film LUT with protected highlights',
  Epic: 'high-latitude blockbuster LUT with heroic highlight roll-off',
  Dark: 'noir teal-black LUT with restrained saturation',
  Minimal: 'neutral filmic LUT with honest color separation',
  Sport: 'punchy performance LUT with clean blacks',
  Neo: 'saturated cyan-magenta neo-city LUT',
};

export const cameraPresetNames = ['Hero Walk', 'Orbit', 'Tracking', 'Crane', 'Drone', 'Static'] as const;
export type CameraPresetName = (typeof cameraPresetNames)[number];

export type CameraPreset = {
  name: CameraPresetName;
  camera: string;
  lens: string;
  lighting: string;
  motion: string;
};

export const CAMERA_PRESETS: Record<CameraPresetName, CameraPreset> = {
  'Hero Walk': {
    name: 'Hero Walk',
    camera: 'Hero Walk',
    lens: '35mm anamorphic',
    lighting: 'motivated hero key with controlled rim light',
    motion: 'low-angle dolly tracking with confident forward energy',
  },
  Orbit: {
    name: 'Orbit',
    camera: 'Orbit',
    lens: '50mm',
    lighting: 'soft wrap with specular separation',
    motion: 'controlled orbit around the subject to reveal shape and intent',
  },
  Tracking: {
    name: 'Tracking',
    camera: 'Tracking',
    lens: '35mm',
    lighting: 'directional motivated light that travels with the subject',
    motion: 'side tracking move anchored to the scene objective',
  },
  Crane: {
    name: 'Crane',
    camera: 'Crane',
    lens: '28mm',
    lighting: 'wide cinematic backlight with readable geography',
    motion: 'crane rise that expands scale without changing story intent',
  },
  Drone: {
    name: 'Drone',
    camera: 'Drone',
    lens: '24mm',
    lighting: 'natural aerial light with preserved highlights',
    motion: 'aerial drift that establishes geography and production value',
  },
  Static: {
    name: 'Static',
    camera: 'Static',
    lens: '50mm',
    lighting: 'single motivated soft source with clean falloff',
    motion: 'locked-off composition; motion comes from performance inside frame',
  },
};

export type StoryboardScene = {
  id: string;
  scene_number: number;
  title: string;
  objective: string;
  emotion: string;
  camera: string;
  lens: string;
  lighting: string;
  motion: string;
  duration: number;
  environment: string;
  mood: SceneMood;
  lut: string;
  prompt: string;
  negative_prompt: string;
  timeline_start: number;
  timeline_end: number;
};

export type StoryboardState = {
  project_id: string;
  production_plan_id: string;
  scenes: StoryboardScene[];
  version: number;
  updated_at: string;
};

export type SceneEditableField =
  | 'title'
  | 'objective'
  | 'emotion'
  | 'camera'
  | 'lens'
  | 'lighting'
  | 'motion'
  | 'duration'
  | 'environment';

export type ScenePatch = Partial<Pick<StoryboardScene, SceneEditableField>>;

export type StoryboardHistory = {
  past: StoryboardState[];
  present: StoryboardState;
  future: StoryboardState[];
  limit: number;
};

type IdFactory = () => string;
type Clock = () => string;

const defaultClock: Clock = () => new Date().toISOString();

export function createSceneId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `scene_${Math.random().toString(36).slice(2)}`;
}

export function normalizeMood(value: string | null | undefined): SceneMood {
  const found = moodOptions.find(option => option.toLowerCase() === String(value ?? '').trim().toLowerCase());
  return found ?? 'Minimal';
}

export function sanitizeDuration(value: number): number {
  return Number.isFinite(value) && value > 0 ? value : MIN_SCENE_DURATION;
}

export function roundTimeline(value: number): number {
  return Number(value.toFixed(TIMELINE_PRECISION));
}

export function totalDuration(state: StoryboardState): number {
  return roundTimeline(state.scenes.reduce((total, scene) => total + scene.duration, 0));
}

export function withTimeline(scenes: StoryboardScene[]): StoryboardScene[] {
  let cursor = 0;
  return scenes.map((scene, index) => {
    const duration = sanitizeDuration(Number(scene.duration));
    const start = roundTimeline(cursor);
    cursor += duration;
    const nextSceneNumber = FIRST_SCENE_NUMBER + index;
    const nextDuration = roundTimeline(duration);
    const nextEnd = roundTimeline(cursor);
    if (
      scene.scene_number === nextSceneNumber &&
      scene.duration === nextDuration &&
      scene.timeline_start === start &&
      scene.timeline_end === nextEnd
    ) return scene;
    return {
      ...scene,
      scene_number: nextSceneNumber,
      duration: nextDuration,
      timeline_start: start,
      timeline_end: nextEnd,
    };
  });
}

export function sceneFromShot(
  shot: DirectorShotPlan,
  mood: SceneMood,
  idFactory: IdFactory = createSceneId,
): StoryboardScene {
  return {
    id: idFactory(),
    scene_number: shot.scene_number,
    title: shot.title,
    objective: shot.objective,
    emotion: shot.emotion,
    camera: shot.camera,
    lens: shot.lens,
    lighting: shot.lighting,
    motion: shot.motion,
    duration: sanitizeDuration(Number(shot.duration)),
    environment: shot.environment,
    mood,
    lut: MOOD_LUTS[mood],
    prompt: shot.prompt,
    negative_prompt: shot.negative_prompt,
    timeline_start: 0,
    timeline_end: 0,
  };
}

export function createStoryboardState(
  plan: ProductionPlan,
  projectId = 'director-local-project',
  idFactory: IdFactory = createSceneId,
  clock: Clock = defaultClock,
): StoryboardState {
  const mood = normalizeMood(plan.mood);
  return {
    project_id: projectId,
    production_plan_id: plan.id,
    scenes: withTimeline(plan.shots.map(shot => sceneFromShot(shot, mood, idFactory))),
    version: INITIAL_STORYBOARD_VERSION,
    updated_at: clock(),
  };
}

function advance(state: StoryboardState, scenes: StoryboardScene[], clock: Clock = defaultClock): StoryboardState {
  return {
    ...state,
    scenes: withTimeline(scenes),
    version: state.version + 1,
    updated_at: clock(),
  };
}

function findSceneIndex(scenes: StoryboardScene[], sceneId: string): number {
  return scenes.findIndex(scene => scene.id === sceneId);
}

export function updateScene(
  state: StoryboardState,
  sceneId: string,
  patch: ScenePatch,
  clock: Clock = defaultClock,
): StoryboardState {
  let changed = false;
  const scenes = state.scenes.map(scene => {
    if (scene.id !== sceneId) return scene;
    changed = true;
    return {
      ...scene,
      ...patch,
      duration: patch.duration === undefined ? scene.duration : sanitizeDuration(Number(patch.duration)),
    };
  });
  return changed ? advance(state, scenes, clock) : state;
}

export function reorderScene(
  state: StoryboardState,
  sourceSceneId: string,
  targetSceneId: string,
  clock: Clock = defaultClock,
): StoryboardState {
  const from = findSceneIndex(state.scenes, sourceSceneId);
  const to = findSceneIndex(state.scenes, targetSceneId);
  if (from < 0 || to < 0 || from === to) return state;

  const scenes = [...state.scenes];
  const [moved] = scenes.splice(from, 1);
  scenes.splice(to, 0, moved);
  return advance(state, scenes, clock);
}

export function duplicateScene(
  state: StoryboardState,
  sceneId: string,
  idFactory: IdFactory = createSceneId,
  clock: Clock = defaultClock,
): StoryboardState {
  const index = findSceneIndex(state.scenes, sceneId);
  if (index < 0) return state;

  const duplicate = { ...state.scenes[index], id: idFactory() };
  const scenes = [...state.scenes];
  scenes.splice(index + 1, 0, duplicate);
  return advance(state, scenes, clock);
}

export function removeScene(
  state: StoryboardState,
  sceneId: string,
  clock: Clock = defaultClock,
): StoryboardState {
  if (state.scenes.length <= 1) return state;
  const scenes = state.scenes.filter(scene => scene.id !== sceneId);
  return scenes.length === state.scenes.length ? state : advance(state, scenes, clock);
}

export function updateCameraPreset(
  state: StoryboardState,
  sceneId: string,
  presetName: CameraPresetName,
  clock: Clock = defaultClock,
): StoryboardState {
  const preset = CAMERA_PRESETS[presetName];
  return updateScene(
    state,
    sceneId,
    {
      camera: preset.camera,
      lens: preset.lens,
      lighting: preset.lighting,
      motion: preset.motion,
    },
    clock,
  );
}

export function updateSceneMood(
  state: StoryboardState,
  sceneId: string,
  mood: SceneMood,
  clock: Clock = defaultClock,
): StoryboardState {
  let changed = false;
  const scenes = state.scenes.map(scene => {
    if (scene.id !== sceneId) return scene;
    changed = true;
    return { ...scene, mood, lut: MOOD_LUTS[mood] };
  });
  return changed ? advance(state, scenes, clock) : state;
}

export function createStoryboardHistory(present: StoryboardState, limit = STORYBOARD_HISTORY_LIMIT): StoryboardHistory {
  return { past: [], present, future: [], limit };
}

export function commitStoryboardState(history: StoryboardHistory, next: StoryboardState): StoryboardHistory {
  if (next === history.present || next.version === history.present.version) return history;
  return {
    ...history,
    past: [...history.past, history.present].slice(-history.limit),
    present: next,
    future: [],
  };
}

export function undoStoryboard(history: StoryboardHistory): StoryboardHistory {
  if (history.past.length === 0) return history;
  const previous = history.past[history.past.length - 1];
  return {
    ...history,
    past: history.past.slice(0, -1),
    present: previous,
    future: [history.present, ...history.future].slice(0, history.limit),
  };
}

export function redoStoryboard(history: StoryboardHistory): StoryboardHistory {
  if (history.future.length === 0) return history;
  const [next, ...future] = history.future;
  return {
    ...history,
    past: [...history.past, history.present].slice(-history.limit),
    present: next,
    future,
  };
}
