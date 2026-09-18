/**
 * PR013 — V4.0.1 Cinematic Asset Studio: the pure library domain.
 *
 * No React, no DOM, no network: the accept-list, the upload state machine,
 * the filters/search and every formatter/band the components render.
 * The honesty contract is pinned too — unknown renders as `—`, never a guess.
 */
import { describe, expect, it } from 'vitest';

import {
  ACCEPTED_EXTENSIONS,
  ACCEPTED_UPLOAD_TYPES,
  EMPTY_LIBRARY_FILTERS,
  SCORE_BAND_LABELS,
  SCORE_FLOOR_OPTIONS,
  UNKNOWN_LABEL,
  UPLOAD_ACCEPT_ATTR,
  collectFacets,
  completeUpload,
  countLibrary,
  createUploadItem,
  failUpload,
  filterLibrary,
  filtersAreActive,
  formatBytes,
  formatDuration,
  formatLibraryDate,
  formatSpeed,
  hasActiveUploads,
  markUploading,
  matchesLibraryFilters,
  partitionUploads,
  progressUpload,
  resolutionLabel,
  resolveUploadMime,
  scoreBand,
  uploadKindFor,
  type LibraryAsset,
  type LibraryFilters,
} from './library';

// ---------------------------------------------------------------------------
// The file fixture factory — only the fields a test actually cares about.
// ---------------------------------------------------------------------------

let sequence = 0;

function asset(overrides: Partial<LibraryAsset> = {}): LibraryAsset {
  sequence += 1;
  return {
    id: `asset-${sequence}`,
    name: `Scene ${sequence}.png`,
    kind: 'image',
    url: `/files/asset-${sequence}`,
    created_at: '2026-08-12T11:22:33Z',
    has_metadata: true,
    project: 'Brobond',
    persona: 'Ayla',
    provider: 'flux',
    seed: 4200 + sequence,
    width: 1920,
    height: 1080,
    tags: ['neon', 'portrait'],
    quality_score: 90,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// ETAPA 1 — the accept-list
// ---------------------------------------------------------------------------

describe('upload accept-list', () => {
  it('accepts exactly the five media types of the sprint', () => {
    expect(Object.keys(ACCEPTED_UPLOAD_TYPES).sort()).toEqual([
      'image/jpeg',
      'image/png',
      'image/webp',
      'video/mp4',
      'video/quicktime',
    ]);
    expect(UPLOAD_ACCEPT_ATTR).toBe('.png,.jpg,.jpeg,.webp,.mp4,.mov');
  });

  it('resolves the mime from the file type first', () => {
    expect(resolveUploadMime({ name: 'take.bin', type: 'video/mp4' })).toBe('video/mp4');
    expect(resolveUploadMime({ name: 'frame.png', type: 'image/png' })).toBe('image/png');
  });

  it('falls back to the extension when the browser leaves type empty (.mov)', () => {
    expect(resolveUploadMime({ name: 'TAKE.MOV', type: '' })).toBe('video/quicktime');
    expect(resolveUploadMime({ name: 'frame.webp', type: '' })).toBe('image/webp');
    expect(resolveUploadMime({ name: 'photo.JPG', type: '' })).toBe('image/jpeg');
    expect(resolveUploadMime({ name: 'photo.jpeg', type: '' })).toBe('image/jpeg');
    expect(Object.keys(ACCEPTED_EXTENSIONS)).not.toContain('gif');
  });

  it('rejects anything outside the list — no silent misclassification', () => {
    expect(resolveUploadMime({ name: 'notes.txt', type: 'text/plain' })).toBeNull();
    expect(resolveUploadMime({ name: 'no_extension', type: '' })).toBeNull();
    expect(resolveUploadMime({ name: 'archive.zip', type: 'application/zip' })).toBeNull();
    expect(uploadKindFor({ name: 'clip.gif', type: 'image/gif' })).toBeNull();
  });

  it('maps resolved mimes to the right kind', () => {
    expect(uploadKindFor({ name: 'a.mp4', type: 'video/mp4' })).toBe('video');
    expect(uploadKindFor({ name: 'a.png', type: 'image/png' })).toBe('image');
    expect(uploadKindFor({ name: 'a.mov', type: '' })).toBe('video');
  });

  it('partitions a mixed drop into accepted and rejected', () => {
    const files = [
      { name: 'a.png', type: 'image/png' },
      { name: 'b.txt', type: 'text/plain' },
      { name: 'c.mov', type: '' },
      { name: 'd.exe', type: 'application/x-msdownload' },
    ];
    const { accepted, rejected } = partitionUploads(files);
    expect(accepted.map(file => file.name)).toEqual(['a.png', 'c.mov']);
    expect(rejected.map(file => file.name)).toEqual(['b.txt', 'd.exe']);
  });
});

// ---------------------------------------------------------------------------
// ETAPA 1 — the upload queue state machine
// ---------------------------------------------------------------------------

describe('upload queue state machine', () => {
  const file = { name: 'take-01.mp4', type: 'video/mp4', size: 2048 };

  it('creates a queued item with zeroed progress', () => {
    const item = createUploadItem('up-1', file, 'video');
    expect(item).toEqual({
      id: 'up-1',
      name: 'take-01.mp4',
      size: 2048,
      kind: 'video',
      status: 'queued',
      percent: 0,
      bytesPerSecond: 0,
    });
  });

  it('transitions queued → uploading → completed with real percent', () => {
    let item = createUploadItem('up-2', file, 'video');
    item = markUploading(item);
    expect(item.status).toBe('uploading');
    item = progressUpload(item, 1024, 2048, 512_000);
    expect(item).toMatchObject({ status: 'uploading', percent: 50, bytesPerSecond: 512_000 });
    item = completeUpload(item);
    expect(item).toMatchObject({ status: 'completed', percent: 100 });
  });

  it('caps the percentage at 100 when the loaded count overshoots a stale total', () => {
    const item = progressUpload(createUploadItem('up-3', file, 'video'), 4096, 2048, 1);
    expect(item.percent).toBe(100);
  });

  it('keeps the previous percentage when the total is not computable', () => {
    const item = { ...createUploadItem('up-4', file, 'video'), percent: 37 };
    expect(progressUpload(item, 9000, 0, 44).percent).toBe(37);
  });

  it('records failures with the exact error text — never an invented retry', () => {
    const failed = failUpload(createUploadItem('up-5', file, 'video'), 'Server answered 413');
    expect(failed).toMatchObject({ status: 'failed', error: 'Server answered 413' });
  });

  it('reports active uploads only while something is queued or in flight', () => {
    const idle = [completeUpload(createUploadItem('a', file, 'video')), failUpload(createUploadItem('b', file, 'video'), 'x')];
    expect(hasActiveUploads(idle)).toBe(false);
    expect(hasActiveUploads([...idle, createUploadItem('c', file, 'video')])).toBe(true);
    expect(hasActiveUploads([...idle, markUploading(createUploadItem('d', file, 'video'))])).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// ETAPA 5 — filters and instant search
// ---------------------------------------------------------------------------

describe('library filters and search', () => {
  const list = [
    asset({ name: 'Lobby wide.png', kind: 'image', project: 'Brobond', persona: 'Ayla', provider: 'flux', quality_score: 96, created_at: '2026-08-10T02:00:00Z' }),
    asset({ name: 'Take 07.mp4', kind: 'video', project: 'Nocturne', persona: 'Rin', provider: 'wan', quality_score: 72, created_at: '2026-08-12T22:00:00Z', tags: ['rain'] }),
    asset({ name: 'Portrait v3.png', kind: 'image', project: 'Brobond', persona: null, provider: 'flux', quality_score: null, created_at: '2026-08-13T01:00:00Z', tags: [] }),
  ];

  const withFilters = (overrides: Partial<LibraryFilters>): LibraryFilters => ({ ...EMPTY_LIBRARY_FILTERS, ...overrides });

  it('starts with every filter inactive', () => {
    expect(filtersAreActive(EMPTY_LIBRARY_FILTERS)).toBe(false);
    expect(filterLibrary(list, EMPTY_LIBRARY_FILTERS)).toHaveLength(3);
  });

  it('filters by kind', () => {
    expect(filterLibrary(list, withFilters({ kind: 'video' })).map(item => item.name)).toEqual(['Take 07.mp4']);
    expect(filterLibrary(list, withFilters({ kind: 'image' }))).toHaveLength(2);
    expect(filtersAreActive(withFilters({ kind: 'image' }))).toBe(true);
  });

  it('filters by project, persona and provider case-insensitively', () => {
    expect(filterLibrary(list, withFilters({ project: 'brobond' }))).toHaveLength(2);
    expect(filterLibrary(list, withFilters({ persona: 'RIN' }))).toHaveLength(1);
    expect(filterLibrary(list, withFilters({ provider: 'Wan' }))).toHaveLength(1);
    // A NULL facet never matches a chosen value — unknown is not "everything".
    expect(filterLibrary(list, withFilters({ persona: 'ayla' })).map(item => item.name)).toEqual(['Lobby wide.png']);
    expect(filterLibrary(list, withFilters({ project: 'nocturne' }))).toHaveLength(1);
    expect(filterLibrary(list, withFilters({ provider: 'flux' }))).toHaveLength(2);
    // Entries whose own facet is NULL never leak through a chosen facet value.
    const orphan = asset({ name: 'Orphan.png', project: null, provider: null });
    expect(matchesLibraryFilters(orphan, withFilters({ project: 'brobond' }))).toBe(false);
    expect(matchesLibraryFilters(orphan, withFilters({ provider: 'flux' }))).toBe(false);
    expect(matchesLibraryFilters(orphan, withFilters({}))).toBe(true);
  });

  it('applies the quality floor; unscored entries drop out under any floor', () => {
    expect(filterLibrary(list, withFilters({ minScore: 95 })).map(item => item.name)).toEqual(['Lobby wide.png']);
    expect(filterLibrary(list, withFilters({ minScore: 70 }))).toHaveLength(2);
    expect(filterLibrary(list, withFilters({ minScore: 0 }))).toHaveLength(3);
  });

  it('bounds by creation date on either side', () => {
    expect(filterLibrary(list, withFilters({ dateFrom: '2026-08-11' }))).toHaveLength(2);
    expect(filterLibrary(list, withFilters({ dateTo: '2026-08-10' }))).toHaveLength(1);
    expect(filterLibrary(list, withFilters({ dateFrom: '2026-08-11', dateTo: '2026-08-12' }))).toHaveLength(1);
  });

  it('searches name, tags and kind instantly', () => {
    expect(filterLibrary(list, withFilters({ search: 'rain' })).map(item => item.name)).toEqual(['Take 07.mp4']);
    // "portrait" hits one tag (Lobby) and one name (Portrait v3) — both surfaces search.
    expect(filterLibrary(list, withFilters({ search: 'portrait' }))).toHaveLength(2);
    expect(filterLibrary(list, withFilters({ search: 'mp4' }))).toHaveLength(1);
    // An entry with no tags at all still searches its name and kind.
    const tagless = asset({ name: 'Bare frame.png', tags: undefined });
    expect(matchesLibraryFilters(tagless, withFilters({ search: 'bare' }))).toBe(true);
    expect(matchesLibraryFilters(tagless, withFilters({ search: 'neon' }))).toBe(false);
    expect(filterLibrary(list, withFilters({ search: 'zzz' }))).toHaveLength(0);
    expect(filterLibrary(list, withFilters({ search: '   ' }))).toHaveLength(3);
  });

  it('combines every cut at once', () => {
    const strict = withFilters({ kind: 'video', project: 'Nocturne', provider: 'wan', minScore: 70, search: 'take' });
    expect(filterLibrary(list, strict).map(item => item.name)).toEqual(['Take 07.mp4']);
    expect(matchesLibraryFilters(list[0], strict)).toBe(false);
  });

  it('collects unique, sorted facets and ignores blanks', () => {
    const facets = collectFacets(list);
    expect(facets.projects).toEqual(['Brobond', 'Nocturne']);
    expect(facets.personas).toEqual(['Ayla', 'Rin']);
    expect(facets.providers).toEqual(['flux', 'wan']);
    expect(collectFacets([])).toEqual({ projects: [], personas: [], providers: [] });
  });

  it('counts the library by kind', () => {
    expect(countLibrary(list)).toEqual({ all: 3, image: 2, video: 1 });
    expect(countLibrary([])).toEqual({ all: 0, image: 0, video: 0 });
  });
});

// ---------------------------------------------------------------------------
// ETAPA 3/6 — formatters and bands (unknown → em dash, never a guess)
// ---------------------------------------------------------------------------

describe('presentation helpers', () => {
  it('formats bytes across units and refuses unknowns', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2048)).toBe('2.0 KB');
    expect(formatBytes(1_500_000)).toBe('1.4 MB');
    expect(formatBytes(250_000_000)).toBe('238 MB');
    expect(formatBytes(3 * 1024 * 1024 * 1024)).toBe('3.0 GB');
    expect(formatBytes(null)).toBe(UNKNOWN_LABEL);
    expect(formatBytes(-5)).toBe(UNKNOWN_LABEL);
    expect(formatBytes(Number.NaN)).toBe(UNKNOWN_LABEL);
  });

  it('formats speed only for positive throughput', () => {
    expect(formatSpeed(1_048_576)).toBe('1.0 MB/s');
    expect(formatSpeed(0)).toBe(UNKNOWN_LABEL);
    expect(formatSpeed(undefined)).toBe(UNKNOWN_LABEL);
  });

  it('formats durations as mm:ss', () => {
    expect(formatDuration(0)).toBe('00:00');
    expect(formatDuration(65)).toBe('01:05');
    expect(formatDuration(599.4)).toBe('09:59');
    expect(formatDuration(null)).toBe(UNKNOWN_LABEL);
  });

  it('formats library dates and rejects garbage timestamps', () => {
    expect(formatLibraryDate('2026-08-12T11:22:33Z')).toBe('Aug 12, 2026');
    expect(formatLibraryDate('not-a-date')).toBe(UNKNOWN_LABEL);
    expect(formatLibraryDate(null)).toBe(UNKNOWN_LABEL);
  });

  it('labels resolution from the real metadata only', () => {
    expect(resolutionLabel({ resolution: '1920×1080' })).toBe('1920×1080');
    expect(resolutionLabel({ width: 3840, height: 2160 })).toBe('3840×2160');
    expect(resolutionLabel({})).toBe(UNKNOWN_LABEL);
  });

  it('bands quality scores exactly on the Quality Engine thresholds', () => {
    expect(scoreBand(69)).toBe('retry');
    expect(scoreBand(70)).toBe('review');
    expect(scoreBand(84)).toBe('review');
    expect(scoreBand(85)).toBe('approved');
    expect(scoreBand(94)).toBe('approved');
    expect(scoreBand(95)).toBe('masterpiece');
    expect(scoreBand(null)).toBe('unscored');
    expect(scoreBand(undefined)).toBe('unscored');
    expect(SCORE_BAND_LABELS.masterpiece).toBe('Masterpiece');
    expect(SCORE_BAND_LABELS.unscored).toBe('Unscored');
  });

  it('offers only the real score floors', () => {
    expect(SCORE_FLOOR_OPTIONS.map(option => option.value)).toEqual([0, 70, 85, 95]);
  });
});
