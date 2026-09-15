'use client';

import { useMemo, useState } from 'react';
import { Search, UserRound, Zap } from 'lucide-react';
import type { PersonaImageRef, PersonaProfile } from '../../../lib/api';

type PersonaSelectorProps = {
  /** The workspace personas (fetched by the caller — the selector is pure). */
  personas: PersonaProfile[];
  /** The currently selected persona id (or `null` for free composition). */
  selectedId: string | null;
  /** Report the selection upward; `null` clears the active identity. */
  onSelect: (persona: PersonaProfile | null) => void;
};

/**
 * PR004 (ETAPA 1) — the reusable Persona selector.
 *
 * Shared by the Image Studio and the Video Studio: it lists the personas of
 * the workspace, searches them by name, shows the avatar, the default style
 * and a badge when a LoRA is trained, and reports the selection upward.
 *
 * The data arrives as a prop on purpose: the component stays presentational,
 * renders deterministically (testable without the API) and degrades to an
 * honest empty state when the workspace has no personas yet.
 */

/** The main portrait: a face shot wins, then the first image with a URL. */
export function mainImage(persona: PersonaProfile): PersonaImageRef | null {
  const images = persona.images ?? [];
  return (
    images.find(image => image.image_type === 'face' && image.url) ??
    images.find(image => image.url) ??
    null
  );
}

export default function PersonaSelector({ personas, selectedId, onSelect }: PersonaSelectorProps) {
  const [query, setQuery] = useState('');
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const list = needle ? personas.filter(persona => persona.name.toLowerCase().includes(needle)) : personas;
    return [...list].sort((a, b) => a.name.localeCompare(b.name));
  }, [personas, query]);

  return <div className="persona-selector">
    <div className="persona-selector-search">
      <Search size={13} />
      <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search persona..." />
    </div>
    <div className="persona-selector-list">
      <button type="button" className={!selectedId ? 'selected' : ''} onClick={() => onSelect(null)}>
        <span className="persona-avatar"><UserRound size={14} /></span>
        <span className="persona-line"><strong>Free composition</strong><small>No identity — prompt only</small></span>
      </button>
      {visible.map(persona => {
        const image = mainImage(persona);
        return <button key={persona.id} type="button" className={persona.id === selectedId ? 'selected' : ''} onClick={() => onSelect(persona)}>
          <span className="persona-avatar">{image?.url ? <img src={image.url!} alt={persona.name} /> : <UserRound size={14} />}</span>
          <span className="persona-line"><strong>{persona.name}</strong><small>{persona.default_style || 'no default style'}</small></span>
          {persona.lora_id ? <span className="persona-lora-badge" title="A trained LoRA exists for this persona"><Zap size={10} /> LoRA</span> : <span className="persona-lora-none" title="No LoRA trained yet">—</span>}
        </button>;
      })}
      {visible.length === 0 && <small className="persona-empty">No persona matches “{query}”.</small>}
    </div>
  </div>;
}
