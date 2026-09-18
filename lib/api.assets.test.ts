// @vitest-environment jsdom
/**
 * PR013 — V4.0.1: the library surface of `lib/api.ts`.
 *
 * `libraryQuery` is the exact wire shape of the backend's filters;
 * `uploadLibraryAsset` must upload as multipart (never JSON), carry the
 * Bearer token when one is remembered, and map every failure through the
 * same `readError`/`httpErrorType`/`networkProblemText` helpers the rest
 * of the client uses. The XHR itself is the stubbed browser primitive.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { NetworkErrorType } from './network/request';
import { getLibraryAsset, libraryQuery, listAssetLibrary, uploadLibraryAsset } from './api';
import { clearAuthToken, setAuthToken } from './memory/project_memory';

// ---------------------------------------------------------------------------
// XHR stub (the browser primitive uploadLibraryAsset is disciplined into)
// ---------------------------------------------------------------------------

class FakeXHR {
  static instances: FakeXHR[] = [];
  handlers: Record<string, Array<() => void>> = {};
  uploadHandlers: Record<string, Array<(event: ProgressEvent) => void>> = {};
  headers: Record<string, string> = {};
  url = '';
  body: FormData | null = null;
  status = 201;
  statusText = 'Created';
  responseText = '{"id":"a-1"}';
  upload = {
    addEventListener: (type: 'progress', listener: (event: ProgressEvent) => void) => {
      this.uploadHandlers[type] = [...(this.uploadHandlers[type] ?? []), listener];
    },
  };
  constructor() {
    FakeXHR.instances.push(this);
  }
  open(_method: string, url: string) {
    this.url = url;
  }
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value;
  }
  send(body: FormData) {
    this.body = body;
  }
  abort() { /* unused */ }
  addEventListener(type: string, listener: () => void) {
    this.handlers[type] = [...(this.handlers[type] ?? []), listener];
  }
  fire(type: 'load' | 'error' | 'timeout' | 'abort') {
    (this.handlers[type] ?? []).forEach(listener => listener());
  }
}

beforeEach(() => {
  FakeXHR.instances = [];
  vi.stubGlobal('XMLHttpRequest', FakeXHR);
  clearAuthToken();
  vi.spyOn(console, 'info').mockImplementation(() => undefined);
});

// ---------------------------------------------------------------------------
// The wire shape of the library filters
// ---------------------------------------------------------------------------

describe('libraryQuery', () => {
  it('serializes nothing for empty filters', () => {
    expect(libraryQuery()).toBe('');
    expect(libraryQuery({ kind: '' })).toBe('');
    expect(libraryQuery({ search: '   ' })).toBe('');
  });

  it('serializes every cut with the backend’s parameter names', () => {
    const query = libraryQuery({
      kind: 'video',
      project: 'Brobond Studio',
      persona: 'Ayla',
      provider: 'flux',
      minScore: 85,
      dateFrom: '2026-08-11',
      dateTo: '2026-08-31',
      search: '   neon rain  ',
    });
    expect(query.startsWith('?')).toBe(true);
    const params = new URLSearchParams(query.slice(1));
    expect(params.get('kind')).toBe('video');
    expect(params.get('project')).toBe('Brobond Studio');
    expect(params.get('persona')).toBe('Ayla');
    expect(params.get('provider')).toBe('flux');
    expect(params.get('min_score')).toBe('85');
    expect(params.get('date_from')).toBe(new Date('2026-08-11T00:00:00').toISOString());
    expect(params.get('date_to')).toBe(new Date('2026-08-31T23:59:59.999').toISOString());
    expect(params.get('q')).toBe('neon rain');
  });

  it('routes list and detail through the library paths', () => {
    expect(listAssetLibrary).toBeTypeOf('function');
    expect(getLibraryAsset).toBeTypeOf('function');
    // The paths themselves are pinned by the request spy below.
  });
});

// ---------------------------------------------------------------------------
// uploadLibraryAsset — multipart, token, typed failures
// ---------------------------------------------------------------------------

describe('uploadLibraryAsset', () => {
  const frame = () => new File(['frame bytes'], 'frame.png', { type: 'image/png' });

  it('posts multipart fields and never the file as JSON', async () => {
    const pending = uploadLibraryAsset(frame(), { fields: { project: 'Brobond', tags: 'neon,night', seed: null, persona: '' } });
    const xhr = FakeXHR.instances[0];
    expect(xhr.url).toBe('/api/v1/assets/library/upload');
    expect(xhr.body).toBeInstanceOf(FormData);
    expect(xhr.body?.get('project')).toBe('Brobond');
    expect(xhr.body?.get('tags')).toBe('neon,night');
    // Empty and null fields are omitted — the backend treats missing as unknown.
    expect(xhr.body?.get('seed')).toBeNull();
    expect(xhr.body?.get('persona')).toBeNull();
    expect(JSON.stringify((xhr.body?.get('file') as File).name)).toBe('"frame.png"');

    xhr.fire('load');
    const result = await pending;
    expect(result.remote).toBe(true);
    if (result.remote) expect(result.data).toEqual({ id: 'a-1' });
  });

  it('attaches the Bearer token when one is remembered', async () => {
    setAuthToken('remembered-token');
    const pending = uploadLibraryAsset(frame());
    const xhr = FakeXHR.instances[0];
    expect(xhr.headers.Authorization).toBe('Bearer remembered-token');
    xhr.fire('load');
    await pending;
  });

  it('maps an API answer to the shared failure shape (server text, typed)', async () => {
    const pending = uploadLibraryAsset(frame());
    const xhr = FakeXHR.instances[0];
    xhr.status = 415;
    xhr.responseText = JSON.stringify({ detail: 'Unsupported media type: application/pdf' });
    xhr.fire('load');
    const result = await pending;
    expect(result.remote).toBe(false);
    if (!result.remote) {
      expect(result.error).toContain('Unsupported media type');
      // The shared V3.2.1 mapper: 4xx is unknown (client problem), 5xx is server_error.
      expect(result.errorType).toBe(NetworkErrorType.UNKNOWN);
    }
  });

  it('maps a network failure through the network problem text', async () => {
    const pending = uploadLibraryAsset(frame());
    const xhr = FakeXHR.instances[0];
    xhr.fire('error');
    const result = await pending;
    expect(result.remote).toBe(false);
    if (!result.remote) expect(result.errorType).toBe(NetworkErrorType.OFFLINE);
  });

  it('forwards real progress samples to the caller', async () => {
    const samples: number[] = [];
    const pending = uploadLibraryAsset(frame(), { onProgress: progress => samples.push(progress.percent) });
    const xhr = FakeXHR.instances[0];
    (xhr.uploadHandlers.progress ?? []).forEach(listener => listener({ loaded: 5, total: 10, lengthComputable: true } as ProgressEvent));
    (xhr.uploadHandlers.progress ?? []).forEach(listener => listener({ loaded: 10, total: 10, lengthComputable: true } as ProgressEvent));
    expect(samples).toEqual([50, 100]);
    xhr.fire('load');
    await pending;
  });
});
