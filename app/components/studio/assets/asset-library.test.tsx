// @vitest-environment jsdom
/**
 * PR013 — V4.0.1 — the orchestrator's contract, end to end.
 *
 * `lib/api` is the only mocked boundary (the network itself is covered in
 * `lib/network/upload.test.ts`). Everything else — drop zone, queue, filter
 * bar, grid, preview, empty states — is the production module, so this
 * suite reads exactly like the Definition of Done.
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { LibraryAsset } from '../../../../lib/assets/library';

vi.mock('../../../../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../../../../lib/api')>('../../../../lib/api');
  return {
    ...actual,
    listAssetLibrary: vi.fn(),
    uploadLibraryAsset: vi.fn(),
  };
});

import { NetworkErrorType, listAssetLibrary, uploadLibraryAsset } from '../../../../lib/api';
import type { UploadProgress } from '../../../../lib/api';
import { AssetLibraryClient } from './asset-library';

const listMock = vi.mocked(listAssetLibrary);
const uploadMock = vi.mocked(uploadLibraryAsset);

let sequence = 0;

function asset(overrides: Partial<LibraryAsset> = {}): LibraryAsset {
  sequence += 1;
  return {
    id: `lib-${sequence}`,
    name: `Scene ${sequence}.png`,
    kind: 'image',
    url: `/files/scene-${sequence}.png`,
    created_at: '2026-08-12T11:22:33Z',
    has_metadata: true,
    project: 'Brobond',
    persona: 'Ayla',
    provider: 'flux',
    seed: 1000 + sequence,
    width: 1920,
    height: 1080,
    resolution: '1920×1080',
    tags: ['neon'],
    quality_score: 90,
    thumbnail_url: `/files/thumbs/scene-${sequence}.jpg`,
    ...overrides,
  };
}

function pngFile(name = 'frame.png', size = 100_000) {
  return new File([new Uint8Array(size)], name, { type: 'image/png' });
}

function drop(files: File[]) {
  const zone = screen.getByTestId('al-dropzone');
  fireEvent.dragEnter(zone, { dataTransfer: { files, types: ['Files'], dropEffect: '' } });
  fireEvent.drop(zone, { dataTransfer: { files, types: ['Files'], dropEffect: '' } });
}

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void };

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(resolver => {
    resolve = resolver;
  });
  return { promise, resolve };
}

beforeEach(() => {
  listMock.mockReset();
  uploadMock.mockReset();
});

describe('read + classify', () => {
  it('shows a calm loading line before any answer', async () => {
    listMock.mockReturnValue(new Promise(() => undefined) as never);
    render(<AssetLibraryClient />);
    expect(screen.getByText('Reading the library…')).toBeInTheDocument();
    await act(async () => Promise.resolve());
  });

  it('renders the real library with counted totals', async () => {
    const onCounted = vi.fn();
    const entries = [asset(), asset({ kind: 'video', name: 'Take 09.mp4' })];
    listMock.mockResolvedValue({ remote: true, data: entries } as never);
    render(<AssetLibraryClient onCounted={onCounted} />);

    expect(await screen.findByTestId('al-grid')).toBeInTheDocument();
    expect(screen.getByTestId('al-filters')).toBeInTheDocument();
    expect(onCounted).toHaveBeenCalledWith({ all: 2, image: 1, video: 1 });
    expect(screen.getByText('Take 09.mp4')).toBeInTheDocument();
  });

  it('maps an unreachable API to the no-connection state and retries on demand', async () => {
    listMock
      .mockResolvedValueOnce({ remote: false, error: 'offline', errorType: NetworkErrorType.OFFLINE } as never)
      .mockResolvedValueOnce({ remote: true, data: [asset()] } as never);
    render(<AssetLibraryClient />);

    expect(await screen.findByTestId('al-empty-offline')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Try again/ }));
    expect(await screen.findByTestId('al-grid')).toBeInTheDocument();
    expect(listMock).toHaveBeenCalledTimes(2);
  });

  it('treats CORS and cold-start timeouts as no-connection too', async () => {
    listMock.mockResolvedValueOnce({ remote: false, error: 'cors', errorType: NetworkErrorType.CORS } as never);
    const { unmount } = render(<AssetLibraryClient />);
    expect(await screen.findByTestId('al-empty-offline')).toBeInTheDocument();
    unmount();

    listMock.mockResolvedValue({ remote: false, error: 'timeout', errorType: NetworkErrorType.TIMEOUT } as never);
    render(<AssetLibraryClient />);
    expect(await screen.findByTestId('al-empty-offline')).toBeInTheDocument();
    expect(screen.getByText('timeout')).toBeInTheDocument();
  });

  it('retries from the error state as well', async () => {
    listMock
      .mockResolvedValueOnce({ remote: false, error: '500 Internal Server Error', errorType: NetworkErrorType.SERVER_ERROR } as never)
      .mockResolvedValueOnce({ remote: true, data: [] } as never);
    render(<AssetLibraryClient />);
    expect(await screen.findByTestId('al-empty-error')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Try again/ }));
    expect(await screen.findByTestId('al-empty-empty')).toBeInTheDocument();
  });

  it('shows the server’s own words on a plain API error', async () => {
    listMock.mockResolvedValue({ remote: false, error: '401 Unauthorized', errorType: NetworkErrorType.UNAUTHORIZED } as never);
    render(<AssetLibraryClient />);
    expect(await screen.findByTestId('al-empty-error')).toBeInTheDocument();
    expect(screen.getByText('401 Unauthorized')).toBeInTheDocument();
  });

  it('keeps the empty library cinematic, restaged on retry', async () => {
    listMock.mockResolvedValue({ remote: true, data: [] } as never);
    render(<AssetLibraryClient />);
    expect(await screen.findByTestId('al-empty-empty')).toBeInTheDocument();
  });
});

describe('filters and search (instant, in memory)', () => {
  it('narrows the grid as you type and owns the empty cut', async () => {
    const entries = [
      asset({ name: 'Lobby wide.png', tags: ['neon'] }),
      asset({ name: 'Take 07.mp4', kind: 'video', tags: ['rain'] }),
    ];
    listMock.mockResolvedValue({ remote: true, data: entries } as never);
    render(<AssetLibraryClient />);
    await screen.findByTestId('al-grid');

    expect(screen.getByText('2 assets')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Search by name or tag'), { target: { value: 'rain' } });
    expect(screen.getByText('1 of 2')).toBeInTheDocument();
    expect(screen.queryByText('Lobby wide.png')).toBeNull();
    expect(screen.getByText('Take 07.mp4')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Search by name or tag'), { target: { value: 'zzz' } });
    expect(await screen.findByTestId('al-empty-filtered')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Clear filters/ }));
    expect(screen.getByTestId('al-grid')).toBeInTheDocument();
    expect(screen.getByText('2 assets')).toBeInTheDocument();
  });

  it('cuts by kind tab and facet select', async () => {
    listMock.mockResolvedValue({
      remote: true,
      data: [asset({ project: 'Brobond' }), asset({ kind: 'video', name: 'Take 02.mp4', project: 'Nocturne' })],
    } as never);
    render(<AssetLibraryClient />);
    await screen.findByTestId('al-grid');

    fireEvent.click(screen.getByRole('button', { name: 'Videos' }));
    expect(screen.queryByText('Scene 1.png')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'All types' }));
    fireEvent.change(screen.getByLabelText('Filter by project'), { target: { value: 'Brobond' } });
    expect(screen.getByText('1 of 2')).toBeInTheDocument();
  });
});

describe('ingest — drops become real queue entries', () => {
  it('uploads a dropped PNG with live progress, then prepends it completed', async () => {
    const onCounted = vi.fn();
    listMock.mockResolvedValue({ remote: true, data: [] } as never);
    const pending = deferred<never>();
    type UploadOptions = Parameters<typeof uploadLibraryAsset>[1];
    let capturedProgress: ((progress: UploadProgress) => void) | undefined;
    uploadMock.mockImplementation((_file: File, options?: UploadOptions) => {
      capturedProgress = options?.onProgress;
      return pending.promise;
    });
    render(<AssetLibraryClient onCounted={onCounted} />);
    await screen.findByTestId('al-empty-empty');

    drop([pngFile('frame-01.png')]);
    expect(await screen.findByText('frame-01.png')).toBeInTheDocument();
    expect(screen.getByText('Uploading')).toBeInTheDocument();
    // ETAPA 1's exact telemetry: percentage and speed are read, not simulated.
    await act(async () => {
      capturedProgress?.({ loaded: 50_000, total: 100_000, percent: 50, bytesPerSecond: 25_000, at: Date.now() });
      await Promise.resolve();
    });
    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.getByText('24.4 KB/s')).toBeInTheDocument();

    const fresh = asset({ id: 'fresh-1', name: 'frame-01.png' });
    await act(async () => {
      pending.resolve({ remote: true, data: fresh } as never);
      await pending.promise;
    });
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByTestId('al-grid')).toBeInTheDocument();
    expect(onCounted).toHaveBeenLastCalledWith({ all: 1, image: 1, video: 0 });
  });

  it('processes a multi-file drop strictly in order', async () => {
    listMock.mockResolvedValue({ remote: true, data: [] } as never);
    const first = deferred<never>();
    const calls: string[] = [];
    uploadMock.mockImplementation((file: File) => {
      calls.push(file.name);
      if (file.name === 'a.png') return first.promise;
      return Promise.resolve({ remote: true, data: asset({ name: file.name }) } as never);
    });
    render(<AssetLibraryClient />);
    await screen.findByTestId('al-empty-empty');

    await act(async () => {
      drop([pngFile('a.png'), pngFile('b.png'), pngFile('c.png')]);
      await Promise.resolve();
    });
    expect(calls).toEqual(['a.png']);

    await act(async () => {
      first.resolve({ remote: true, data: asset({ name: 'a.png' }) } as never);
      await first.promise;
    });
    expect(calls).toEqual(['a.png', 'b.png', 'c.png']);
    expect(await screen.findAllByText('Completed')).toHaveLength(3);
  });

  it('keeps a failed upload failed, with the server’s words beside it', async () => {
    listMock.mockResolvedValue({ remote: true, data: [asset()] } as never);
    uploadMock.mockResolvedValue({ remote: false, error: 'Server answered 415', errorType: NetworkErrorType.SERVER_ERROR } as never);
    render(<AssetLibraryClient />);
    await screen.findByTestId('al-grid');

    await act(async () => {
      drop([pngFile('bad.png')]);
      await Promise.resolve();
    });
    expect(screen.getByText('Failed')).toBeInTheDocument();
    expect(screen.getByText('Server answered 415')).toBeInTheDocument();
    // The library itself never pretends the file arrived.
    expect(screen.getByText('1 assets')).toBeInTheDocument();
  });

  it('falls back to "Upload failed" when the failure carries no text', async () => {
    listMock.mockResolvedValue({ remote: true, data: [] } as never);
    uploadMock.mockResolvedValue({ remote: false } as never);
    render(<AssetLibraryClient />);
    await screen.findByTestId('al-empty-empty');

    await act(async () => {
      drop([pngFile('quiet.png')]);
      await Promise.resolve();
    });
    expect(screen.getByText('Failed')).toBeInTheDocument();
    expect(screen.getByText('Upload failed')).toBeInTheDocument();
  });

  it('refuses files outside the sprint types, honestly, and clears the notice on a clean drop', async () => {
    listMock.mockResolvedValue({ remote: true, data: [] } as never);
    uploadMock.mockResolvedValue({ remote: true, data: asset() } as never);
    render(<AssetLibraryClient />);
    await screen.findByTestId('al-empty-empty');

    await act(async () => {
      drop([new File(['x'], 'notes.txt', { type: 'text/plain' }), new File(['x'], 'app.exe', { type: '' })]);
      await Promise.resolve();
    });
    expect(screen.getByTestId('al-notice')).toHaveTextContent('notes.txt, app.exe');
    expect(uploadMock).not.toHaveBeenCalled();

    await act(async () => {
      drop([pngFile('clean.png')]);
      await Promise.resolve();
    });
    expect(screen.queryByTestId('al-notice')).toBeNull();
    expect(uploadMock).toHaveBeenCalledTimes(1);
  });

  it('shows the uploading state while the first-ever ingest runs', async () => {
    listMock.mockResolvedValue({ remote: true, data: [] } as never);
    const pending = deferred<never>();
    uploadMock.mockReturnValue(pending.promise);
    render(<AssetLibraryClient />);
    await screen.findByTestId('al-empty-empty');

    await act(async () => {
      drop([pngFile('first.png')]);
      await Promise.resolve();
    });
    expect(screen.getByTestId('al-empty-uploading')).toBeInTheDocument();
    await act(async () => {
      pending.resolve({ remote: true, data: asset() } as never);
      await pending.promise;
    });
  });

  it('hands the page a queue entry through registerEnqueue', async () => {
    listMock.mockResolvedValue({ remote: true, data: [] } as never);
    uploadMock.mockResolvedValue({ remote: true, data: asset() } as never);
    let enqueue: ((files: File[]) => void) | undefined;
    render(<AssetLibraryClient registerEnqueue={handler => { enqueue = handler; }} />);
    await screen.findByTestId('al-empty-empty');

    await act(async () => {
      enqueue?.([pngFile('picked.png')]);
      await Promise.resolve();
    });
    expect(uploadMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText('picked.png')).toBeInTheDocument();
  });
});

describe('preview', () => {
  it('opens from a card and closes back to the grid', async () => {
    listMock.mockResolvedValue({ remote: true, data: [asset({ name: 'Lobby.png' })] } as never);
    render(<AssetLibraryClient />);
    await screen.findByTestId('al-grid');

    fireEvent.click(screen.getByRole('button', { name: 'Open Lobby.png' }));
    expect(screen.getByTestId('al-lightbox')).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByTestId('al-lightbox')).toBeNull();
    expect(screen.getByTestId('al-grid')).toBeInTheDocument();
  });
});
