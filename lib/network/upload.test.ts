// @vitest-environment jsdom
/**
 * PR013 — V4.0.1 Cinematic Asset Studio: the upload runner's own contract.
 *
 * jsdom's XHR never completes against a vitest run, so every scenario here
 * drives events through a fake transport exactly the way `runUpload`'s
 * factory seam allows; the mapping code under test is the production one:
 * progress → percent/bps, network events → typed NetworkError, response →
 * a real `Response` the caller can pass to `readError`/`httpErrorType`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { NetworkErrorType } from './request';

type Handler = () => void;

/** The smallest UploadTransport implementation the runner exercises. */
class FakeTransport {
  handlers: Record<string, Handler[]> = {};
  uploadHandlers: Record<string, Array<(event: ProgressEvent) => void>> = {};
  headers: Record<string, string> = {};
  method = '';
  url = '';
  body: FormData | null = null;
  timeout = 0;
  status = 201;
  statusText = 'Created';
  responseText = '{"ok":true}';
  upload = {
    addEventListener: (type: 'progress', listener: (event: ProgressEvent) => void) => {
      this.uploadHandlers[type] = [...(this.uploadHandlers[type] ?? []), listener];
    },
  };
  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value;
  }
  send(body: FormData) {
    this.body = body;
  }
  abort() { /* the runner never aborts on its own */ }
  addEventListener(type: string, listener: Handler) {
    this.handlers[type] = [...(this.handlers[type] ?? []), listener];
  }
  fire(type: 'load' | 'error' | 'timeout' | 'abort') {
    (this.handlers[type] ?? []).forEach(listener => listener());
  }
  progress(options: { loaded: number; total?: number; computable?: boolean; at?: number }) {
    const event = {
      loaded: options.loaded,
      total: options.total ?? 0,
      lengthComputable: options.computable ?? true,
    } as ProgressEvent;
    (this.uploadHandlers.progress ?? []).forEach(listener => listener(event));
  }
}

async function freshModule(apiUrl?: string) {
  vi.resetModules();
  if (apiUrl === undefined) delete process.env.NEXT_PUBLIC_API_URL;
  else process.env.NEXT_PUBLIC_API_URL = apiUrl;
  return import('./upload');
}

afterEach(() => {
  delete process.env.NEXT_PUBLIC_API_URL;
  vi.restoreAllMocks();
});

describe('runUpload — the transport boundary', () => {
  it('posts a multipart body with the trace header and resolves the real Response', async () => {
    const { runUpload } = await freshModule();
    const transport = new FakeTransport();
    const logSpy = vi.spyOn(console, 'info').mockImplementation(() => undefined);

    const pending = runUpload('/api/v1/assets/library/upload', {
      file: new Blob(['frame bytes'], { type: 'image/png' }),
      filename: 'frame.png',
      fields: { project: 'Brobond', tags: 'neon,night' },
    }, () => transport as never);

    expect(transport.method).toBe('POST');
    expect(transport.url).toBe('/api/v1/assets/library/upload');
    expect(transport.body?.get('project')).toBe('Brobond');
    expect(transport.body?.get('tags')).toBe('neon,night');
    const uploaded = transport.body?.get('file');
    expect(uploaded).toBeInstanceOf(File);
    expect((uploaded as File).name).toBe('frame.png');
    expect(transport.timeout).toBe(60000);
    expect(transport.headers['x-brobond-trace']).toMatch(/^upl-|^.{8}-/);

    transport.fire('load');
    const outcome = await pending;
    expect(outcome.kind).toBe('response');
    if (outcome.kind === 'response') {
      expect(outcome.response.status).toBe(201);
      expect(await outcome.response.json()).toEqual({ ok: true });
      expect(logSpy).toHaveBeenCalledWith(expect.stringContaining(outcome.traceId));
      expect(logSpy).toHaveBeenCalledWith(expect.stringContaining('POST /api/v1/assets/library/upload -> 201'));
    }
  });

  it('reports percent and bytes-per-second from progress events', async () => {
    const { runUpload } = await freshModule();
    const transport = new FakeTransport();
    const samples: Array<{ percent: number; bytesPerSecond: number; total: number }> = [];

    const pending = runUpload('/x', {
      file: new Blob(['x']),
      onProgress: progress => samples.push(progress),
    }, () => transport as never);

    transport.progress({ loaded: 25, total: 100 });
    transport.progress({ loaded: 50, total: 100 });
    expect(samples.map(sample => sample.percent)).toEqual([25, 50]);
    expect(samples[0].total).toBe(100);
    expect(samples[0].bytesPerSecond).toBeGreaterThan(0);

    transport.progress({ loaded: 75, computable: false });
    expect(samples[2].percent).toBe(0);
    expect(samples[2].total).toBe(0);

    transport.progress({ loaded: 300, total: 100 });
    expect(samples[3].percent).toBe(100);

    transport.fire('load');
    await pending;
  });

  it('tolerates uploads with no progress listener and no upload tunnel', async () => {
    const { runUpload } = await freshModule();
    const transport = new FakeTransport();
    Object.defineProperty(transport, 'upload', { value: null });
    const pending = runUpload('/x', { file: new Blob(['x']) }, () => transport as never);
    transport.fire('load');
    const outcome = await pending;
    expect(outcome.kind).toBe('response');
  });

  it('drops progress frames when the caller never asked for them', async () => {
    const { runUpload } = await freshModule();
    const transport = new FakeTransport();
    const pending = runUpload('/x', { file: new Blob(['x']) }, () => transport as never);
    transport.progress({ loaded: 10, total: 100 });
    transport.fire('load');
    const outcome = await pending;
    expect(outcome.kind).toBe('response');
  });

  it('maps a network failure to OFFLINE on a same-origin API', async () => {
    const { runUpload } = await freshModule();
    const transport = new FakeTransport();
    const pending = runUpload('/x', { file: new Blob(['x']) }, () => transport as never);
    transport.fire('error');
    const outcome = await pending;
    expect(outcome.kind).toBe('error');
    if (outcome.kind === 'error') expect(outcome.error.type).toBe(NetworkErrorType.OFFLINE);
  });

  it('maps a network failure to CORS when the API lives on another origin', async () => {
    const { runUpload } = await freshModule('https://api.brobond.example');
    const transport = new FakeTransport();
    const pending = runUpload('/x', { file: new Blob(['x']) }, () => transport as never);
    expect(transport.url).toBe('https://api.brobond.example/x');
    transport.fire('error');
    const outcome = await pending;
    expect(outcome.kind).toBe('error');
    if (outcome.kind === 'error') expect(outcome.error.type).toBe(NetworkErrorType.CORS);
  });

  it('maps timeout and abort to the TIMEOUT class', async () => {
    const { runUpload } = await freshModule();
    const first = new FakeTransport();
    const timeoutOutcome = await (async () => {
      const pending = runUpload('/x', { file: new Blob(['x']), timeoutMs: 5000 }, () => first as never);
      expect(first.timeout).toBe(5000);
      first.fire('timeout');
      return pending;
    })();
    expect(timeoutOutcome.kind).toBe('error');
    if (timeoutOutcome.kind === 'error') expect(timeoutOutcome.error.type).toBe(NetworkErrorType.TIMEOUT);

    const second = new FakeTransport();
    const abortOutcome = await (async () => {
      const pending = runUpload('/x', { file: new Blob(['x']) }, () => second as never);
      second.fire('abort');
      return pending;
    })();
    if (abortOutcome.kind === 'error') expect(abortOutcome.error.type).toBe(NetworkErrorType.TIMEOUT);
  });

  it('turns a throwing open() into OFFLINE instead of an unhandled rejection', async () => {
    const { runUpload } = await freshModule();
    const transport = new FakeTransport();
    transport.open = () => { throw new Error('bad url'); };
    const outcome = await runUpload('http://://', { file: new Blob(['x']) }, () => transport as never);
    expect(outcome.kind).toBe('error');
    if (outcome.kind === 'error') expect(outcome.error.type).toBe(NetworkErrorType.OFFLINE);
  });

  it('turns a throwing transport factory into OFFLINE as well', async () => {
    const { runUpload } = await freshModule();
    const outcome = await runUpload('/x', { file: new Blob(['x']) }, () => {
      throw new Error('no XHR here');
    });
    expect(outcome.kind).toBe('error');
    if (outcome.kind === 'error') expect(outcome.error.type).toBe(NetworkErrorType.OFFLINE);
  });

  it('builds its default transport from XMLHttpRequest', async () => {
    const { runUpload } = await freshModule();
    const built: FakeTransport[] = [];
    class FakeXHR extends FakeTransport {
      constructor() {
        super();
        built.push(this);
      }
    }
    vi.stubGlobal('XMLHttpRequest', FakeXHR);
    const pending = runUpload('/x', { file: new Blob(['x']) });
    expect(built).toHaveLength(1);
    built[0].fire('load');
    const outcome = await pending;
    expect(outcome.kind).toBe('response');
    vi.unstubAllGlobals();
  });

  it('falls back to a dated trace id when crypto.randomUUID is unavailable', async () => {
    const original = globalThis.crypto;
    vi.stubGlobal('crypto', { randomUUID: undefined });
    const { runUpload } = await freshModule();
    const transport = new FakeTransport();
    const pending = runUpload('/x', { file: new Blob(['x']) }, () => transport as never);
    expect(transport.headers['x-brobond-trace']).toMatch(/^upl-/);
    transport.fire('load');
    await pending;
    vi.stubGlobal('crypto', original);
    vi.unstubAllGlobals();
  });

  it('keeps the request field name and headers of the caller', async () => {
    const { runUpload } = await freshModule();
    const transport = new FakeTransport();
    const pending = runUpload('/x', {
      file: new Blob(['x']),
      fieldName: 'payload',
      headers: { authorization: 'Bearer tok' },
    }, () => transport as never);
    expect(transport.headers.authorization).toBe('Bearer tok');
    expect(transport.body?.get('payload')).toBeTruthy();
    transport.fire('load');
    await pending;
  });
});

describe('cross-origin detection edges', () => {
  beforeEach(() => {
    vi.spyOn(console, 'info').mockImplementation(() => undefined);
  });

  it('treats an unparsable http API_URL as cross-origin rather than guessing', async () => {
    const { runUpload } = await freshModule('http://');
    const transport = new FakeTransport();
    const pending = runUpload('/x', { file: new Blob(['x']) }, () => transport as never);
    transport.fire('error');
    const outcome = await pending;
    expect(outcome.kind).toBe('error');
    if (outcome.kind === 'error') expect(outcome.error.type).toBe(NetworkErrorType.CORS);
  });
});
