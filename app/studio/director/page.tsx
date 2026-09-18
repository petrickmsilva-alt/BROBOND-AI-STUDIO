'use client';

import { useEffect, useMemo, useState } from 'react';
import { Clock3, Clapperboard, Film, History, MessageSquareText, Redo2, Sparkles, Undo2, UserRound } from 'lucide-react';
import type { PersonaProfile, ProductionPlan } from '../../../lib/api';
import { failureMessage } from '../../../lib/network/status';
import { createProductionPlan, listPersonaProfiles } from '../../../lib/api';
import type { CameraPresetName, SceneMood, ScenePatch, StoryboardHistory, StoryboardState } from '../../../lib/storyboard/storyboard_state';
import {
  commitStoryboardState,
  createSceneId,
  createStoryboardHistory,
  createStoryboardState,
  duplicateScene,
  moodOptions,
  redoStoryboard,
  removeScene,
  reorderScene,
  totalDuration,
  undoStoryboard,
  updateCameraPreset,
  updateScene,
  updateSceneMood,
} from '../../../lib/storyboard/storyboard_state';
import { CameraPanel } from './CameraPanel';
import { MoodPanel } from './MoodPanel';
import { SceneInspector } from './SceneInspector';
import { Timeline } from './Timeline';
// PR012 — ETAPA 7: the cinematic Storyboard Cards replace the previous
// StoryboardCanvas. Same props, same reorder/select wiring against the
// untouched StoryboardState — visual only.
import { StoryboardCards, type StoryboardCardScene } from '../../../components/studio/storyboard-cards';

const platformOptions = [
  { value: 'instagram', label: 'Instagram' },
  { value: 'reels', label: 'Reels' },
  { value: 'tiktok', label: 'TikTok' },
  { value: 'youtube', label: 'YouTube' },
  { value: 'cinema', label: 'Cinema' },
  { value: 'web', label: 'Web' },
  { value: 'ads', label: 'Ads' },
];

export default function DirectorPage() {
  const [intent, setIntent] = useState('');
  const [personaId, setPersonaId] = useState('');
  const [platform, setPlatform] = useState('instagram');
  const [duration, setDuration] = useState(30);
  const [mood, setMood] = useState<SceneMood>('Minimal');
  const [personas, setPersonas] = useState<PersonaProfile[]>([]);
  const [plan, setPlan] = useState<ProductionPlan | null>(null);
  const [history, setHistory] = useState<StoryboardHistory | null>(null);
  const [selectedSceneId, setSelectedSceneId] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const storyboard = history?.present ?? null;
  const selectedScene = useMemo(
    () => storyboard?.scenes.find(scene => scene.id === selectedSceneId) ?? storyboard?.scenes[0],
    [selectedSceneId, storyboard],
  );

  useEffect(() => {
    listPersonaProfiles().then(result => {
      if (result.remote) setPersonas(result.data);
    });
  }, []);

  useEffect(() => {
    if (!storyboard?.scenes.length) {
      setSelectedSceneId(undefined);
      return;
    }
    if (!selectedSceneId || !storyboard.scenes.some(scene => scene.id === selectedSceneId)) {
      setSelectedSceneId(storyboard.scenes[0].id);
    }
  }, [selectedSceneId, storyboard]);

  const create = async () => {
    if (!intent.trim()) return;
    setLoading(true);
    setError(undefined);
    const result = await createProductionPlan({
      user_intent: intent.trim(),
      persona_id: personaId || null,
      platform,
      duration,
      mood,
    });
    if (result.remote) {
      const state = createStoryboardState(result.data, 'director-studio-project', createSceneId);
      setPlan(result.data);
      setHistory(createStoryboardHistory(state));
      setSelectedSceneId(state.scenes[0]?.id);
    } else {
      setPlan(null);
      setHistory(null);
      setSelectedSceneId(undefined);
      setError(failureMessage(result, 'API offline — inicie o FastAPI para criar o plano.'));
    }
    setLoading(false);
  };

  const commit = (mutate: (state: StoryboardState) => StoryboardState) => {
    setHistory(current => {
      if (!current) return current;
      const next = mutate(current.present);
      return commitStoryboardState(current, next);
    });
  };

  const updateSelectedScene = (sceneId: string, patch: ScenePatch) => {
    commit(state => updateScene(state, sceneId, patch));
  };

  const duplicateSelectedScene = (sceneId: string) => {
    commit(state => {
      const next = duplicateScene(state, sceneId, createSceneId);
      const originalIndex = state.scenes.findIndex(scene => scene.id === sceneId);
      const duplicateId = next.scenes[originalIndex + 1]?.id;
      if (duplicateId) setSelectedSceneId(duplicateId);
      return next;
    });
  };

  const removeSelectedScene = (sceneId: string) => {
    commit(state => {
      const next = removeScene(state, sceneId);
      if (!next.scenes.some(scene => scene.id === selectedSceneId)) setSelectedSceneId(next.scenes[0]?.id);
      return next;
    });
  };

  const undo = () => setHistory(current => (current ? undoStoryboard(current) : current));
  const redo = () => setHistory(current => (current ? redoStoryboard(current) : current));

  return <main className="director-page">
    <section className="director-hero">
      <div>
        <div className="eyebrow"><Sparkles size={13} /> PR006 · STORYBOARD CINEMATIC ENGINE</div>
        <h1>Editor cinematográfico visual para o plano de produção.</h1>
        <p>Reordene cenas, ajuste timeline, câmera e mood por cena, duplique ou remova sem acionar Providers e sem gerar imagens.</p>
      </div>
      <span className="director-hero-badge"><Film size={14} /> editing only</span>
    </section>

    <section className="director-workbench storyboard-workbench">
      <div className="control-panel director-request-panel">
        <div className="panel-heading"><span>Brief humano</span><span className="muted">sem prompt técnico</span></div>
        <label className="director-big-field">
          O que você quer criar hoje?
          <textarea value={intent} onChange={event => setIntent(event.target.value)} placeholder="O que você quer criar hoje?" />
        </label>
        <div className="director-form-grid">
          <label>Persona
            <select value={personaId} onChange={event => setPersonaId(event.target.value)}>
              <option value="">Sem persona fixa</option>
              {personas.map(persona => <option key={persona.id} value={persona.id}>{persona.name}</option>)}
            </select>
          </label>
          <label>Plataforma
            <select value={platform} onChange={event => setPlatform(event.target.value)}>
              {platformOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label>Duração
            <input type="number" min={6} max={600} value={duration} onChange={event => setDuration(Number(event.target.value))} />
          </label>
          <label>Mood
            <select value={mood} onChange={event => setMood(event.target.value as SceneMood)}>
              {moodOptions.map(option => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>
        </div>
        {error && <div className="notice notice-error"><MessageSquareText size={13} /><span>{error}</span></div>}
        <button className="primary-button full" onClick={create} disabled={loading || !intent.trim()}>{loading ? 'Criando Produção…' : <><Sparkles size={16} /> Criar Produção</>}</button>
      </div>

      <div className="brief-canvas director-plan-canvas storyboard-editor-shell">
        {!plan || !storyboard ? <div className="empty-canvas">
          <div className="empty-icon"><Clapperboard size={24} /></div>
          <h3>StoryboardState ainda não criado</h3>
          <p>Crie uma produção para abrir o editor visual versionado. Toda alteração incrementa a versão sem renderizar nada.</p>
        </div> : <>
          <div className="brief-head director-plan-head">
            <div><span className="brief-format">v{storyboard.version} · {plan.mood}</span><h2>{plan.title}</h2><p className="brief-logline">{plan.concept}</p></div>
            <div className="brief-facts">
              <span><Clock3 size={13} /> {totalDuration(storyboard)}s editados</span>
              <span><Film size={13} /> {storyboard.scenes.length} cenas</span>
              <span><UserRound size={13} /> {plan.persona_id ?? 'sem persona'}</span>
              <span><History size={13} /> {storyboard.updated_at}</span>
            </div>
          </div>
          <div className="brief-facts-row">
            <span>Música: {plan.music}</span>
            <span>Voz: {plan.voice}</span>
            <span>Público: {plan.audience}</span>
            <button type="button" className="secondary-button" onClick={undo} disabled={!(history?.past.length)}><Undo2 size={13} /> Undo</button>
            <button type="button" className="secondary-button" onClick={redo} disabled={!(history?.future.length)}><Redo2 size={13} /> Redo</button>
          </div>
          <Timeline
            state={storyboard}
            selectedSceneId={selectedScene?.id}
            onSelectScene={setSelectedSceneId}
            onDurationChange={(sceneId, nextDuration) => commit(state => updateScene(state, sceneId, { duration: nextDuration }))}
          />
          <div className="storyboard-editor-grid">
            <StoryboardCards
              scenes={storyboard.scenes.map((scene): StoryboardCardScene => ({
                id: scene.id,
                sceneNumber: scene.scene_number,
                title: scene.title,
                objective: scene.objective,
                camera: scene.camera,
                lens: scene.lens,
                duration: scene.duration,
                mood: scene.mood,
              }))}
              selectedSceneId={selectedScene?.id}
              onSelectScene={setSelectedSceneId}
              onReorderScene={(sourceSceneId, targetSceneId) => commit(state => reorderScene(state, sourceSceneId, targetSceneId))}
            />
            <div className="storyboard-side-stack">
              <SceneInspector
                scene={selectedScene}
                onUpdateScene={updateSelectedScene}
                onDuplicateScene={duplicateSelectedScene}
                onRemoveScene={removeSelectedScene}
                removeDisabled={storyboard.scenes.length <= 1}
              />
              <CameraPanel scene={selectedScene} onSelectPreset={(sceneId, preset) => commit(state => updateCameraPreset(state, sceneId, preset as CameraPresetName))} />
              <MoodPanel scene={selectedScene} onSelectMood={(sceneId, nextMood) => commit(state => updateSceneMood(state, sceneId, nextMood))} />
            </div>
          </div>
        </>}
      </div>
    </section>
  </main>;
}
