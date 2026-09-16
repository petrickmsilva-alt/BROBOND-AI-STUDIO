'use client';

/**
 * V3.2.1 ETAPA 5 — StatusCenter: one honest state for the whole shell.
 *
 * Probes the two public status routes (through `lib/api` → the retrying
 * network layer) and shows exactly one of five states, each with its color
 * and its action:
 *
 *   Online          green   — everything answered;
 *   Inicializando   amber   — timeout in the cold-start window; keeps
 *                             probing every 3s until the server wakes;
 *   Sem internet    red     — no network / CORS block; action: retry;
 *   Sessão expirada purple  — a probe answered 401; action: sign in again;
 *   Erro interno    red     — a probe answered 5xx; action: retry.
 *
 * This component never calls `fetch` and never compares error strings —
 * the state comes from `deriveStatus` over typed `NetworkErrorType`s.
 */
import { useCallback, useEffect, useState } from 'react';

import { health, readiness } from '../../lib/api';
import {
  STATUS_CENTER_META,
  deriveStatus,
  type StatusCenterState,
} from '../../lib/network/status';

const PROBE_INTERVAL_MS = 3000;

export default function StatusCenter() {
  const [state, setState] = useState<StatusCenterState>('online');

  const probe = useCallback(async () => {
    const [healthResult, readinessResult] = await Promise.all([health(), readiness()]);
    setState(deriveStatus([
      { errorType: healthResult.errorType, status: healthResult.status },
      { errorType: readinessResult.errorType, status: readinessResult.status },
    ]));
  }, []);

  useEffect(() => { probe(); }, [probe]);

  // Browser connectivity flips are free signals — no request needed.
  useEffect(() => {
    const goOffline = () => setState('offline');
    const backOnline = () => { probe(); };
    window.addEventListener('offline', goOffline);
    window.addEventListener('online', backOnline);
    return () => {
      window.removeEventListener('offline', goOffline);
      window.removeEventListener('online', backOnline);
    };
  }, [probe]);

  // While the server is waking up, keep trying — the cold-start window can
  // last up to a minute on Render's free tier (ETAPA 4).
  useEffect(() => {
    if (state !== 'initializing') return;
    const timer = setInterval(() => { probe(); }, PROBE_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [state, probe]);

  const meta = STATUS_CENTER_META[state];
  const retryable = state === 'offline' || state === 'server_error';

  return (
    <div className={`status-center status-${state}`} role="status" title={meta.action}>
      <span className="status-center-dot" style={{ background: meta.color, boxShadow: `0 0 7px ${meta.color}` }} />
      <span className="status-center-label">{meta.label}</span>
      <span className="status-center-action">{meta.action}</span>
      {retryable && <button className="status-center-retry" onClick={() => { probe(); }}>Tentar novamente</button>}
    </div>
  );
}
