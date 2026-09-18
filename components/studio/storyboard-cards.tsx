'use client';

/**
 * PR012 — ETAPA 7: Storyboard Cards.
 *
 * Every scene renders as one cinematic card: thumbnail, scene number,
 * objective, lens, camera, duration and mood. Cards are draggable so they
 * plug straight into the existing reorder wiring on
 * `app/studio/director/page.tsx` (`onReorderScene`, already backed by
 * `lib/storyboard/storyboard_state.ts` — untouched by this PR); this
 * component only supplies the drag handlers and calls back, exactly like
 * the previous `StoryboardCanvas`.
 */
import { Camera, Clock3, Film } from 'lucide-react';

export type StoryboardCardScene = {
  id: string;
  sceneNumber: number;
  title: string;
  objective: string;
  camera: string;
  lens: string;
  duration: number;
  mood: string;
  thumbnailUrl?: string | null;
};

export type StoryboardCardsProps = {
  scenes: StoryboardCardScene[];
  selectedSceneId?: string;
  onSelectScene?: (sceneId: string) => void;
  onReorderScene?: (sourceSceneId: string, targetSceneId: string) => void;
  draggable?: boolean;
};

function CardThumbnail({ scene }: { scene: StoryboardCardScene }) {
  if (scene.thumbnailUrl) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={scene.thumbnailUrl} alt={`Thumbnail for ${scene.title}`} className="bb-story-card-thumb-img" />;
  }
  return (
    <div className="bb-story-card-thumb-placeholder" role="img" aria-label={`Cinematic placeholder for ${scene.title}`}>
      <Film size={20} aria-hidden="true" />
    </div>
  );
}

export function StoryboardCards({
  scenes,
  selectedSceneId,
  onSelectScene,
  onReorderScene,
  draggable = true,
}: StoryboardCardsProps) {
  return (
    <div className="bb-story-cards" role="list" aria-label="Storyboard scenes">
      {scenes.map(scene => (
        <article
          key={scene.id}
          role="listitem"
          className={`bb-story-card ${selectedSceneId === scene.id ? 'bb-story-card-selected' : ''}`}
          tabIndex={0}
          aria-selected={selectedSceneId === scene.id}
          draggable={draggable}
          onClick={() => onSelectScene?.(scene.id)}
          onKeyDown={event => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              onSelectScene?.(scene.id);
            }
          }}
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
            const sourceId = event.dataTransfer.getData('text/plain');
            if (sourceId && sourceId !== scene.id) onReorderScene?.(sourceId, scene.id);
          }}
        >
          <CardThumbnail scene={scene} />
          <div className="bb-story-card-body">
            <div className="bb-story-card-head">
              <span className="bb-story-card-scene">Cena {String(scene.sceneNumber).padStart(2, '0')}</span>
              <span className="bb-story-card-mood">{scene.mood}</span>
            </div>
            <h3 className="bb-story-card-title">{scene.title}</h3>
            <p className="bb-story-card-objective">{scene.objective}</p>
            <dl className="bb-story-card-facts">
              <div>
                <dt><Camera size={11} aria-hidden="true" /> Câmera</dt>
                <dd>{scene.camera}</dd>
              </div>
              <div>
                <dt>Lente</dt>
                <dd>{scene.lens}</dd>
              </div>
              <div>
                <dt><Clock3 size={11} aria-hidden="true" /> Duração</dt>
                <dd>{scene.duration}s</dd>
              </div>
            </dl>
          </div>
        </article>
      ))}
    </div>
  );
}

export default StoryboardCards;
