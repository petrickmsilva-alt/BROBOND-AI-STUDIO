'use client';

/**
 * PR012 — ETAPA 5: the Identity Bar.
 *
 * Sits above the Hero Workspace and stays visible at all times, showing
 * exactly what the current generation will use: avatar, persona name,
 * style, LoRA, palette and a "Ready" status pill. Pure presentational —
 * it renders whatever `IdentityBarProps` it receives; `app/page.tsx`
 * already owns this exact state (`activePersona`, `style`, `selectedLora`,
 * persona LoRA list) so wiring it in is a render-only change.
 */
import { UserRound } from 'lucide-react';

export type IdentityBarStatus = 'ready' | 'no-identity' | 'loading';

export type IdentityBarProps = {
  avatarUrl?: string | null;
  personaName?: string | null;
  style?: string | null;
  lora?: string | null;
  palette?: string[];
  status?: IdentityBarStatus;
};

const STATUS_COPY: Record<IdentityBarStatus, string> = {
  ready: 'Ready',
  'no-identity': 'No identity',
  loading: 'Loading…',
};

export function IdentityBar({
  avatarUrl,
  personaName,
  style,
  lora,
  palette = [],
  status = 'ready',
}: IdentityBarProps) {
  const hasIdentity = Boolean(personaName);
  const effectiveStatus: IdentityBarStatus = hasIdentity ? status : 'no-identity';

  return (
    <section className="bb-identity-bar" role="region" aria-label="Active identity">
      <div className="bb-identity-avatar" aria-hidden={avatarUrl ? undefined : 'true'}>
        {avatarUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={avatarUrl} alt={personaName ? `${personaName} avatar` : 'Persona avatar'} />
        ) : (
          <UserRound size={16} aria-hidden="true" />
        )}
      </div>

      <div className="bb-identity-field bb-identity-name">
        <span className="bb-identity-label">Persona</span>
        <strong>{personaName ?? 'No persona selected'}</strong>
      </div>

      <div className="bb-identity-field">
        <span className="bb-identity-label">Style</span>
        <strong>{style || '—'}</strong>
      </div>

      <div className="bb-identity-field">
        <span className="bb-identity-label">LoRA</span>
        <strong>{lora || 'None'}</strong>
      </div>

      <div className="bb-identity-field bb-identity-palette-field">
        <span className="bb-identity-label">Palette</span>
        <div className="bb-identity-palette" aria-label={`Palette: ${palette.length ? palette.join(', ') : 'default'}`}>
          {(palette.length ? palette : ['#8B5CF6', '#27272A', '#FAFAFA']).map((color, index) => (
            <span key={`${color}-${index}`} className="bb-identity-swatch" style={{ background: color }} />
          ))}
        </div>
      </div>

      <span
        className={`bb-status-pill bb-status-pill-${effectiveStatus}`}
        role="status"
      >
        <i aria-hidden="true" /> {STATUS_COPY[effectiveStatus]}
      </span>
    </section>
  );
}

export default IdentityBar;
