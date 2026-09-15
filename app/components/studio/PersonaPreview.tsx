'use client';

import { UserRound, Zap } from 'lucide-react';
import type { LoraVersion, PersonaProfile } from '../../../lib/api';
import { mainImage } from './PersonaSelector';

type PersonaPreviewProps = {
  /** The active persona; `null` renders the honest empty state. */
  persona: PersonaProfile | null;
  /** The persona's LoRA versions (to label the trained adapter). */
  loras: LoraVersion[];
  /** The wardrobe items the project selected (names). */
  selectedWardrobe: string[];
  /** Toggle one wardrobe item in/out of the selection. */
  onToggleWardrobe: (name: string) => void;
};

/**
 * PR004 (ETAPA 2) — the active persona's identity card.
 *
 * Real-time by construction: it is a pure render of its props, so switching
 * personas in the selector re-renders it instantly (the `key` on the persona
 * id replays the appearance transition). It shows the main image, name,
 * beard, hair, voice, default style, LoRA and the registered wardrobe.
 *
 * The wardrobe chips are selectable: the selection travels with the
 * generation request (`wardrobe`) and is persisted by the Project Memory.
 */
export default function PersonaPreview({ persona, loras, selectedWardrobe, onToggleWardrobe }: PersonaPreviewProps) {
  if (!persona) {
    return <div className="persona-preview empty">
      <div className="empty-icon"><UserRound size={22} /></div>
      <h3>No active identity</h3>
      <p>Select a persona to keep the<br />character consistent across shots.</p>
    </div>;
  }
  const image = mainImage(persona);
  const lora = loras.find(item => item.asset_id === persona.lora_id) ?? loras[0];
  return <div className="persona-preview" key={persona.id}>
    <div className="persona-preview-cover">
      {image?.url ? <img src={image.url} alt={persona.name} /> : <div className="persona-preview-initials">{persona.name.slice(0, 2).toUpperCase()}</div>}
      <span className="persona-preview-revision">v{persona.revision}</span>
    </div>
    <h3 className="persona-preview-name">{persona.name}</h3>
    <dl className="persona-preview-facts">
      <div><dt>Beard</dt><dd>{persona.beard || '—'}</dd></div>
      <div><dt>Hair</dt><dd>{persona.hair || '—'}</dd></div>
      <div><dt>Voice</dt><dd>{persona.voice || '—'}</dd></div>
      <div><dt>Default style</dt><dd>{persona.default_style || '—'}</dd></div>
      <div><dt>LoRA</dt><dd>{persona.lora_id ? (lora?.version ?? 'trained') : 'not trained'}</dd></div>
    </dl>
    <div className="persona-preview-wardrobe">
      <span className="persona-preview-label">Wardrobe <em>{persona.wardrobe.length ? `${selectedWardrobe.length}/${persona.wardrobe.length} selected` : 'no items registered'}</em></span>
      {persona.wardrobe.length === 0 ? <small className="persona-empty">No clothes registered for this persona yet.</small> : <div className="chip-row">{persona.wardrobe.map(item => <button key={item.name} type="button" className={`chip ${selectedWardrobe.includes(item.name) ? 'active' : ''}`} title={item.category} onClick={() => onToggleWardrobe(item.name)}>{item.name}</button>)}</div>}
    </div>
    {persona.lora_id && <span className="persona-lora-foot"><Zap size={11} /> LoRA applied automatically on generation</span>}
  </div>;
}
