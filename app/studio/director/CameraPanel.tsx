'use client';

import { Camera } from 'lucide-react';
import type { CameraPresetName, StoryboardScene } from '../../../lib/storyboard/storyboard_state';
import { CAMERA_PRESETS, cameraPresetNames } from '../../../lib/storyboard/storyboard_state';

type CameraPanelProps = {
  scene?: StoryboardScene;
  onSelectPreset: (sceneId: string, presetName: CameraPresetName) => void;
};

export function CameraPanel({ scene, onSelectPreset }: CameraPanelProps) {
  return <aside className="storyboard-panel camera-panel" aria-label="CameraPanel">
    <div className="panel-heading"><span>CameraPanel</span><Camera size={14} /></div>
    <p className="panel-hint">Selecionar um preset atualiza somente o CameraDirector da cena: câmera, lente, luz e movimento.</p>
    <div className="preset-list">
      {cameraPresetNames.map(name => {
        const preset = CAMERA_PRESETS[name];
        const selected = Boolean(scene && scene.camera === preset.camera);
        return <button
          type="button"
          key={name}
          className={selected ? 'selected' : ''}
          disabled={!scene}
          onClick={() => scene && onSelectPreset(scene.id, name)}
        >
          <strong>{name}</strong>
          <span>{preset.lens} · {preset.motion}</span>
        </button>;
      })}
    </div>
  </aside>;
}
