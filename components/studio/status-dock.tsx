'use client';

/**
 * PR012 — ETAPA 6: the Status Dock.
 *
 * Replaces the old sidebar "Readiness" list with a single bottom bar,
 * never taller than 52px (`layout.statusDockHeight`), showing six
 * indicators — API, Database, Storage, GPU, FLUX, WAN — each colored
 * dynamically from `IndicatorState`. This component is purely
 * presentational: `app/page.tsx` already reads `readiness()` /
 * `gpuInfo()` / `listProviders()` through the existing (untouched)
 * `lib/api.ts` contract, and can map those results onto
 * `StatusDockIndicator[]` without any backend change.
 */
import { indicatorColor, layout, type IndicatorState } from '../../lib/theme/tokens';

export type StatusDockIndicatorId = 'api' | 'database' | 'storage' | 'gpu' | 'flux' | 'wan';

export type StatusDockIndicator = {
  id: StatusDockIndicatorId;
  label: string;
  state: IndicatorState;
  detail?: string;
};

export type StatusDockProps = {
  indicators: StatusDockIndicator[];
};

const STATE_LABEL: Record<IndicatorState, string> = {
  online: 'online',
  degraded: 'degraded',
  offline: 'offline',
  unknown: 'unknown',
};

export function StatusDock({ indicators }: StatusDockProps) {
  return (
    <footer
      className="bb-status-dock"
      role="status"
      aria-label="System status"
      style={{ maxHeight: layout.statusDockHeight, height: layout.statusDockHeight }}
    >
      <ul className="bb-status-dock-list">
        {indicators.map(indicator => {
          const color = indicatorColor[indicator.state];
          return (
            <li key={indicator.id} className="bb-status-dock-item" title={indicator.detail ?? `${indicator.label}: ${STATE_LABEL[indicator.state]}`}>
              <span
                className="bb-status-dock-dot"
                aria-hidden="true"
                style={{ background: color, boxShadow: `0 0 6px ${color}` }}
              />
              <span className="bb-status-dock-label">{indicator.label}</span>
              <span className="bb-visually-hidden">{STATE_LABEL[indicator.state]}</span>
            </li>
          );
        })}
      </ul>
    </footer>
  );
}

export default StatusDock;
