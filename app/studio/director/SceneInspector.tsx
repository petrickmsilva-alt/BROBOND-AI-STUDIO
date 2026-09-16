'use client';

import { SlidersHorizontal } from 'lucide-react';
import type { ScenePatch, StoryboardScene } from '../../../lib/storyboard/storyboard_state';

type SceneInspectorProps = {
  scene?: StoryboardScene;
  onUpdateScene: (sceneId: string, patch: ScenePatch) => void;
};

export function SceneInspector({ scene, onUpdateScene }: SceneInspectorProps) {
  if (!scene) {
    return <aside className="storyboard-panel scene-inspector" aria-label="SceneInspector">
      <div className="panel-heading"><span>SceneInspector</span><SlidersHorizontal size={14} /></div>
      <p className="panel-empty">Selecione uma cena para editar título, objetivo, emoção, câmera, lente, iluminação, movimento, duração e ambiente.</p>
    </aside>;
  }

  const update = (patch: ScenePatch) => onUpdateScene(scene.id, patch);

  return <aside className="storyboard-panel scene-inspector" aria-label="SceneInspector">
    <div className="panel-heading"><span>SceneInspector</span><span className="muted">Cena {scene.scene_number}</span></div>
    <label>Título
      <input value={scene.title} onChange={event => update({ title: event.target.value })} />
    </label>
    <label>Objetivo
      <textarea value={scene.objective} onChange={event => update({ objective: event.target.value })} />
    </label>
    <div className="director-shot-fields">
      <label>Emoção
        <input value={scene.emotion} onChange={event => update({ emotion: event.target.value })} />
      </label>
      <label>Duração
        <input type="number" min="0.1" step="0.1" value={scene.duration} onChange={event => update({ duration: Number(event.target.value) })} />
      </label>
      <label>Câmera
        <input value={scene.camera} onChange={event => update({ camera: event.target.value })} />
      </label>
      <label>Lente
        <input value={scene.lens} onChange={event => update({ lens: event.target.value })} />
      </label>
    </div>
    <label>Iluminação
      <input value={scene.lighting} onChange={event => update({ lighting: event.target.value })} />
    </label>
    <label>Movimento
      <input value={scene.motion} onChange={event => update({ motion: event.target.value })} />
    </label>
    <label>Ambiente
      <textarea value={scene.environment} onChange={event => update({ environment: event.target.value })} />
    </label>
  </aside>;
}
