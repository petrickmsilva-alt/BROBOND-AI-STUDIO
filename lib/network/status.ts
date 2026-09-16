/**
 * V3.2.1 — Status Center derivation: probe results in, one honest state out.
 *
 * The five states the sprint defines, each with its color and action, live
 * here as data so both the `StatusCenter` component and the tests reason
 * over the same mapping. Priority matters: a timeout (server waking up)
 * outranks a stale 401 from another panel, and "no network" outranks both.
 */
import { NetworkErrorType } from './request';

export type StatusCenterState =
  | 'online'
  | 'initializing'
  | 'offline'
  | 'unauthorized'
  | 'server_error';

export type ProbeSignal = {
  /** Set when the request failed at the network layer. */
  errorType?: NetworkErrorType;
  /** HTTP status when the server answered (even with an error). */
  status?: number;
};

export const STATUS_CENTER_META: Record<
  StatusCenterState,
  { label: string; color: string; action: string }
> = {
  online: { label: 'Online', color: '#61d49b', action: 'Tudo operando — nada a fazer.' },
  initializing: { label: 'Inicializando', color: '#e8c268', action: 'Servidor iniciando — tentando novamente.' },
  offline: { label: 'Sem internet', color: '#f0a9b4', action: 'Verificar a conexão e tentar de novo.' },
  unauthorized: { label: 'Sessão expirada', color: '#b6a6e8', action: 'Entrar novamente.' },
  server_error: { label: 'Erro interno', color: '#f0a9b4', action: 'Tentar novamente em instantes.' },
};

const PRIORITY: StatusCenterState[] = [
  'initializing',
  'offline',
  'unauthorized',
  'server_error',
];

function stateOf(probe: ProbeSignal): StatusCenterState {
  switch (probe.errorType) {
    case NetworkErrorType.TIMEOUT:
      return 'initializing';
    case NetworkErrorType.OFFLINE:
    case NetworkErrorType.CORS:
      return 'offline';
    case NetworkErrorType.UNAUTHORIZED:
      return 'unauthorized';
    case NetworkErrorType.SERVER_ERROR:
      return 'server_error';
    default:
      return probe.status !== undefined && probe.status >= 500 ? 'server_error' : 'online';
  }
}

/** One state for the whole panel: the worst honest news across the probes,
 * in the priority order above. */
export function deriveStatus(probes: ProbeSignal[]): StatusCenterState {
  const states = probes.map(stateOf);
  for (const candidate of PRIORITY) {
    if (states.includes(candidate)) return candidate;
  }
  return 'online';
}

/**
 * True when no server could have answered — no network, a CORS block, or a
 * timeout (any duration: a cold start is also "the server did not answer
 * *yet*"). Panels use this where behavior differs, not strings.
 */
export function isUnreachable(result: { errorType?: NetworkErrorType }): boolean {
  return (
    result.errorType === NetworkErrorType.OFFLINE ||
    result.errorType === NetworkErrorType.CORS ||
    result.errorType === NetworkErrorType.TIMEOUT
  );
}

/**
 * The message a failed `ApiResult` should show, ETAPA 7 style: the UI never
 * re-derives "offline" from strings. Network classes that mean "no server
 * answered" take the caller's guidance line (each panel knows what the user
 * was trying to do); everything else explains itself — a TIMEOUT already
 * carries the cold-start text ("Servidor iniciando…") from the layer.
 */
export function failureMessage(
  result: { error?: string; errorType?: NetworkErrorType },
  unreachableText: string,
): string {
  if (result.errorType === NetworkErrorType.OFFLINE || result.errorType === NetworkErrorType.CORS) {
    return unreachableText;
  }
  return result.error ?? unreachableText;
}
