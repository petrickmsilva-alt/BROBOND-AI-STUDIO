/**
 * PR013 — V4.0.1: the upload runner without a DOM.
 *
 * The jsdom suite exercises the browser path; this file pins the one thing
 * jsdom can never be — a runtime with no `window`: cross-origin detection
 * must fall back to comparing against the configured API origin instead of
 * crashing, and a transport factory that throws (no XHR in this runtime)
 * still resolves as a typed OFFLINE, never an unhandled rejection.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { NetworkErrorType } from './request';
import { runUpload, type UploadTransport } from './upload';

/** A minimal transport that can banter failure without a DOM. */
function throwingNetworkTransport(): UploadTransport {
  const listeners: Record<string, Array<() => void>> = {};
  return {
    open: () => undefined,
    setRequestHeader: () => undefined,
    send: () => queueMicrotask(() => (listeners.error ?? []).forEach(listener => listener())),
    abort: () => undefined,
    timeout: 0,
    upload: null,
    addEventListener(type, listener) {
      listeners[type] = [...(listeners[type] ?? []), listener];
    },
    status: 0,
    statusText: '',
    responseText: '',
  };
}

afterEach(() => {
  delete process.env.NEXT_PUBLIC_API_URL;
});

describe('runUpload — node runtime', () => {
  it('classifies a same-origin failure as OFFLINE when no window exists', async () => {
    process.env.NEXT_PUBLIC_API_URL = 'https://api.brobond.invalid';
    vi.resetModules();
    const { runUpload: windowlessUpload } = await import('./upload');
    const outcome = await windowlessUpload('/api/v1/assets/library/upload', { file: new Blob(['x']) }, throwingNetworkTransport);
    expect(outcome.kind).toBe('error');
    if (outcome.kind === 'error') expect(outcome.error.type).toBe(NetworkErrorType.OFFLINE);
  });

  it('maps a throwing factory to OFFLINE (no XMLHttpRequest in this runtime)', async () => {
    const outcome = await runUpload('/x', { file: new Blob(['x']) }, () => {
      throw new Error('XMLHttpRequest is not defined');
    });
    expect(outcome.kind).toBe('error');
    if (outcome.kind === 'error') expect(outcome.error.type).toBe(NetworkErrorType.OFFLINE);
  });
});
