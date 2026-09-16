'use client';

import { Copy, GripVertical, Trash2 } from 'lucide-react';
import type { StoryboardScene } from '../../../lib/storyboard/storyboard_state';

type StoryboardCanvasProps = {
  scenes: StoryboardScene[];
  selectedSceneId?: string;
  onSelectScene: (sceneId: string) => void;
  onReorderScene: (sourceSceneId: string, targetSceneId: string) => void;
  onDuplicateScene: (sceneId: string) => void;
  onRemoveScene: (sceneId: string) => void;
};

export function StoryboardCanvas({
  scenes,
  selectedSceneId,
  onSelectScene,
  onReorderScene,
  onDuplicateScene,
  onRemoveScene,
}: StoryboardCanvasProps) {
  return <section className="storyboard-canvas" aria-label="StoryboardCanvas">
    {scenes.map(scene => <article
      key={scene.id}
      className={`storyboard-card ${selectedSceneId === scene.id ? 'selected' : ''}`}
      draggable
      onClick={() => onSelectScene(scene.id)}
      onDragStart={event => {
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', scene.id);
      }}
      onDragOver={event => {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
      }}
      onDrop={event => {
        event.preventDefault();
        const sourceSceneId = event.dataTransfer.getData('text/plain');
        if (sourceSceneId && sourceSceneId !== scene.id) onReorderScene(sourceSceneId, scene.id);
      }}
    >
      <header className="storyboard-card-head">
        <span><GripVertical size={13} /> Cena {String(scene.scene_number).padStart(2, '0')}</span>
        <small>{scene.mood}</small>
      </header>
      <h3>{scene.title}</h3>
      <p>{scene.objective}</p>
      <dl className="storyboard-card-grid">
        <div><dt>Câmera</dt><dd>{scene.camera}</dd></div>
        <div><dt>Lente</dt><dd>{scene.lens}</dd></div>
        <div><dt>Duração</dt><dd>{scene.duration}s</dd></div>
        <div><dt>Emoção</dt><dd>{scene.emotion}</dd></div>
      </dl>
      <footer className="storyboard-card-actions">
        <button type="button" onClick={event => { event.stopPropagation(); onDuplicateScene(scene.id); }}>
          <Copy size={13} /> Duplicar
        </button>
        <button type="button" onClick={event => { event.stopPropagation(); onRemoveScene(scene.id); }} disabled={scenes.length <= 1}>
          <Trash2 size={13} /> Remover
        </button>
      </footer>
    </article>)}
  </section>;
}
