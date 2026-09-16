'use client';

import { Clock3 } from 'lucide-react';
import type { StoryboardScene } from '../../../lib/storyboard/storyboard_state';
import { totalDuration, type StoryboardState } from '../../../lib/storyboard/storyboard_state';

type TimelineProps = {
  state: StoryboardState;
  selectedSceneId?: string;
  onSelectScene: (sceneId: string) => void;
  onDurationChange: (sceneId: string, duration: number) => void;
};

export function Timeline({ state, selectedSceneId, onSelectScene, onDurationChange }: TimelineProps) {
  const total = totalDuration(state);
  return <section className="storyboard-timeline" aria-label="Timeline">
    <header>
      <span><Clock3 size={14} /> Timeline</span>
      <strong>{total}s total</strong>
    </header>
    <div className="timeline-track">
      {state.scenes.map(scene => <div
        key={scene.id}
        className={`timeline-segment ${selectedSceneId === scene.id ? 'selected' : ''}`}
        style={{ flexGrow: scene.duration }}
        onClick={() => onSelectScene(scene.id)}
      >
        <button type="button">C{scene.scene_number}</button>
        <span>{scene.duration}s</span>
      </div>)}
    </div>
    <div className="timeline-resizers">
      {state.scenes.map(scene => <label key={scene.id}>
        C{scene.scene_number}
        <input
          type="range"
          min="0.5"
          max="120"
          step="0.5"
          value={scene.duration}
          aria-label={`Duração da C${scene.scene_number}`}
          onChange={event => onDurationChange(scene.id, Number(event.target.value))}
        />
      </label>)}
    </div>
  </section>;
}
