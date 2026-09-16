/**
 * V3.2.1 ETAPA 5 — StatusCenter derivation: probes in, one honest state out.
 *
 * The mapping is the product decision: a timeout means the server is
 * waking up (never "offline"), a missing network outranks a stale 401,
 * and 5xx is the only thing allowed to say "Erro interno".
 */
import { describe, expect, it } from 'vitest';

import { NetworkErrorType } from './request';
import { STATUS_CENTER_META, deriveStatus, failureMessage, isUnreachable } from './status';

const probe = (errorType?: NetworkErrorType, status?: number) => ({ errorType, status });

describe('deriveStatus', () => {
  it('is online when every probe answered', () => {
    expect(deriveStatus([probe(undefined, 200), probe(undefined, 200)])).toBe('online');
    expect(deriveStatus([])).toBe('online');
  });

  it('reads a timeout as the server initializing — not offline', () => {
    expect(deriveStatus([probe(NetworkErrorType.TIMEOUT)])).toBe('initializing');
  });

  it('reads missing network and CORS blocks as no internet', () => {
    expect(deriveStatus([probe(NetworkErrorType.OFFLINE)])).toBe('offline');
    expect(deriveStatus([probe(NetworkErrorType.CORS)])).toBe('offline');
  });

  it('reads a 401 as an expired session and a 5xx as an internal error', () => {
    expect(deriveStatus([probe(NetworkErrorType.UNAUTHORIZED)])).toBe('unauthorized');
    expect(deriveStatus([probe(NetworkErrorType.SERVER_ERROR)])).toBe('server_error');
    expect(deriveStatus([probe(undefined, 502)])).toBe('server_error');
  });

  it('a 4xx status is not an internal error', () => {
    expect(deriveStatus([probe(undefined, 404)])).toBe('online');
  });

  it('applies the priority: initializing > offline > unauthorized > server_error', () => {
    expect(deriveStatus([probe(NetworkErrorType.SERVER_ERROR), probe(NetworkErrorType.TIMEOUT)])).toBe('initializing');
    expect(deriveStatus([probe(NetworkErrorType.UNAUTHORIZED), probe(NetworkErrorType.OFFLINE)])).toBe('offline');
    expect(deriveStatus([probe(NetworkErrorType.SERVER_ERROR), probe(NetworkErrorType.UNAUTHORIZED)])).toBe(
      'unauthorized',
    );
  });
});

describe('STATUS_CENTER_META', () => {
  it('gives every state a label, a color and an action', () => {
    const states = ['online', 'initializing', 'offline', 'unauthorized', 'server_error'] as const;
    for (const state of states) {
      const meta = STATUS_CENTER_META[state];
      expect(meta.label.length).toBeGreaterThan(0);
      expect(meta.color).toMatch(/^#/);
      expect(meta.action.length).toBeGreaterThan(0);
    }
    // The sprint names the five states exactly.
    expect(STATUS_CENTER_META.initializing.label).toBe('Inicializando');
    expect(STATUS_CENTER_META.offline.label).toBe('Sem internet');
    expect(STATUS_CENTER_META.unauthorized.label).toBe('Sessão expirada');
    expect(STATUS_CENTER_META.server_error.label).toBe('Erro interno');
  });
});

describe('isUnreachable', () => {
  it('is true exactly when no server could have answered', () => {
    expect(isUnreachable({ errorType: NetworkErrorType.OFFLINE })).toBe(true);
    expect(isUnreachable({ errorType: NetworkErrorType.CORS })).toBe(true);
    expect(isUnreachable({ errorType: NetworkErrorType.TIMEOUT })).toBe(true);
    expect(isUnreachable({ errorType: NetworkErrorType.UNAUTHORIZED })).toBe(false);
    expect(isUnreachable({ errorType: NetworkErrorType.SERVER_ERROR })).toBe(false);
    expect(isUnreachable({})).toBe(false);
  });
});

describe('failureMessage', () => {
  const OFFLINE_TEXT = 'API offline — inicie o FastAPI.';

  it("uses the caller's guidance for OFFLINE and CORS", () => {
    expect(failureMessage({ error: 'Sem conexão com a API', errorType: NetworkErrorType.OFFLINE }, OFFLINE_TEXT)).toBe(OFFLINE_TEXT);
    expect(failureMessage({ error: 'bloqueada', errorType: NetworkErrorType.CORS }, OFFLINE_TEXT)).toBe(OFFLINE_TEXT);
  });

  it("lets a timeout speak for itself — the layer's text is cold-start aware", () => {
    expect(
      failureMessage({ error: 'Servidor iniciando — o primeiro acesso pode demorar alguns segundos.', errorType: NetworkErrorType.TIMEOUT }, OFFLINE_TEXT),
    ).toBe('Servidor iniciando — o primeiro acesso pode demorar alguns segundos.');
  });

  it("passes through the server's detail and typed errors", () => {
    expect(failureMessage({ error: 'boom interno', errorType: NetworkErrorType.SERVER_ERROR }, OFFLINE_TEXT)).toBe('boom interno');
    expect(failureMessage({ error: 'Not authenticated', errorType: NetworkErrorType.UNAUTHORIZED }, OFFLINE_TEXT)).toBe('Not authenticated');
  });

  it('falls back to the guidance when there is no message at all', () => {
    expect(failureMessage({}, OFFLINE_TEXT)).toBe(OFFLINE_TEXT);
  });
});
