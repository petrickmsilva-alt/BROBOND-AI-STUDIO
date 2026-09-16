'use client';

import { Palette } from 'lucide-react';
import type { SceneMood, StoryboardScene } from '../../../lib/storyboard/storyboard_state';
import { MOOD_LUTS, moodOptions } from '../../../lib/storyboard/storyboard_state';

type MoodPanelProps = {
  scene?: StoryboardScene;
  onSelectMood: (sceneId: string, mood: SceneMood) => void;
};

export function MoodPanel({ scene, onSelectMood }: MoodPanelProps) {
  return <aside className="storyboard-panel mood-panel" aria-label="MoodPanel">
    <div className="panel-heading"><span>MoodPanel</span><Palette size={14} /></div>
    <p className="panel-hint">Cada cena pode ter mood próprio. A seleção altera apenas mood e LUT do plano.</p>
    <div className="mood-grid">
      {moodOptions.map(mood => <button
        type="button"
        key={mood}
        className={scene?.mood === mood ? 'selected' : ''}
        disabled={!scene}
        onClick={() => scene && onSelectMood(scene.id, mood)}
      >
        <strong>{mood}</strong>
        <span>{MOOD_LUTS[mood]}</span>
      </button>)}
    </div>
    {scene && <div className="lut-readout"><b>LUT atual</b><span>{scene.lut}</span></div>}
  </aside>;
}
