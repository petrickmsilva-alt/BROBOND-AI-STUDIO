/**
 * PR013 — V4.0.1 Cinematic Asset Studio: the pure library domain.
 *
 * Everything here is a pure function over plain data — no React, no
 * network, no DOM. The components in `app/components/studio/assets/`
 * render exactly what these helpers decide; the backend
 * (`backend/app/assets/library_service.py`) accepts the same five media
 * types and mirrors the same NULL-means-unknown rule.
 *
 * Honesty contract (the same the whole repo keeps): an unknown value
 * renders as the em dash `—`, never as a zero, a guessed unit or an
 * invented label.
 */

// ---------------------------------------------------------------------------
// The wire model (mirrors the backend's AssetLibraryEntryResponse)
// ---------------------------------------------------------------------------

export type LibraryAsset = {
  id: string;
  name: string;
  kind: string;
  url: string;
  created_at: string;
  has_metadata: boolean;
  source?: string | null;
  content_type?: string | null;
  size_bytes?: number | null;
  sha256?: string | null;
  resolution?: string | null;
  width?: number | null;
  height?: number | null;
  duration_seconds?: number | null;
  thumbnail_url?: string | null;
  project?: string | null;
  persona?: string | null;
  provider?: string | null;
  seed?: number | null;
  tags?: string[];
  quality_score?: number | null;
  quality_status?: string | null;
  quality_version?: number | null;
  before_asset_id?: string | null;
  before_url?: string | null;
  before_thumbnail_url?: string | null;
};

// ---------------------------------------------------------------------------
// ETAPA 1 — the Upload Engine accept-list (PNG / JPG / WEBP / MP4 / MOV)
// ---------------------------------------------------------------------------

/** MIME → kind, identical to the backend's ACCEPTED_CONTENT_TYPES. */
export const ACCEPTED_UPLOAD_TYPES: Readonly<Record<string, 'image' | 'video'>> = {
  'image/png': 'image',
  'image/jpeg': 'image',
  'image/webp': 'image',
  'video/mp4': 'video',
  'video/quicktime': 'video',
};

/** Extension → MIME, for files whose `type` is empty (`.mov` on some browsers). */
export const ACCEPTED_EXTENSIONS: Readonly<Record<string, keyof typeof ACCEPTED_UPLOAD_TYPES>> = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  webp: 'image/webp',
  mp4: 'video/mp4',
  mov: 'video/quicktime',
};

/** What the file input and the drop zone advertise. */
export const UPLOAD_ACCEPT_ATTR = '.png,.jpg,.jpeg,.webp,.mp4,.mov';

export type FileLike = { name: string; type: string; size: number };

/** Resolve a file to its kind, or null when it is outside the accept-list. */
export function uploadKindFor(file: Pick<FileLike, 'name' | 'type'>): 'image' | 'video' | null {
  const mime = resolveUploadMime(file);
  return mime ? ACCEPTED_UPLOAD_TYPES[mime] : null;
}

export function resolveUploadMime(file: Pick<FileLike, 'name' | 'type'>): string | null {
  if (file.type && file.type in ACCEPTED_UPLOAD_TYPES) return file.type;
  const dot = file.name.lastIndexOf('.');
  if (dot >= 0) {
    const extension = file.name.slice(dot + 1).toLowerCase();
    if (extension in ACCEPTED_EXTENSIONS) return ACCEPTED_EXTENSIONS[extension];
  }
  return null;
}

export function isAcceptedUpload(file: Pick<FileLike, 'name' | 'type'>): boolean {
  return resolveUploadMime(file) !== null;
}

/** Split a mixed drop into accepted files and honest rejections. */
export function partitionUploads<T extends Pick<FileLike, 'name' | 'type'>>(files: readonly T[]): { accepted: T[]; rejected: T[] } {
  const accepted: T[] = [];
  const rejected: T[] = [];
  files.forEach(file => (isAcceptedUpload(file) ? accepted : rejected).push(file));
  return { accepted, rejected };
}

// ---------------------------------------------------------------------------
// ETAPA 1 — the upload queue state machine (pure transitions)
// ---------------------------------------------------------------------------

export type UploadStatus = 'queued' | 'uploading' | 'completed' | 'failed';

export type UploadItem = {
  id: string;
  name: string;
  size: number;
  kind: 'image' | 'video';
  status: UploadStatus;
  /** 0–100 while uploading; 100 when completed. */
  percent: number;
  /** Smoothed throughput of the in-flight request, bytes per second. */
  bytesPerSecond: number;
  /** The failure text when status is 'failed' — never an invented success. */
  error?: string;
};

export function createUploadItem(
  id: string,
  file: Pick<FileLike, 'name' | 'type' | 'size'>,
  kind: 'image' | 'video',
): UploadItem {
  return { id, name: file.name, size: file.size, kind, status: 'queued', percent: 0, bytesPerSecond: 0 };
}

export function markUploading(item: UploadItem): UploadItem {
  return { ...item, status: 'uploading' };
}

export function progressUpload(item: UploadItem, loaded: number, total: number, bytesPerSecond: number): UploadItem {
  const percent = total > 0 ? Math.min(Math.round((loaded / total) * 100), 100) : item.percent;
  return { ...item, status: 'uploading', percent, bytesPerSecond };
}

export function completeUpload(item: UploadItem): UploadItem {
  return { ...item, status: 'completed', percent: 100 };
}

export function failUpload(item: UploadItem, error: string): UploadItem {
  return { ...item, status: 'failed', error };
}

/** True while any item is queued or in flight — drives the "uploading" empty state. */
export function hasActiveUploads(items: readonly UploadItem[]): boolean {
  return items.some(item => item.status === 'queued' || item.status === 'uploading');
}

// ---------------------------------------------------------------------------
// ETAPA 5 — filters and instant search (client-side mirror of the API's own)
// ---------------------------------------------------------------------------

export type LibraryFilters = {
  /** '' means "every kind". */
  kind: '' | 'image' | 'video';
  project: string;
  persona: string;
  provider: string;
  /** 0 disables the score floor; otherwise quality_score must be ≥ this. */
  minScore: number;
  /** ISO date (yyyy-mm-dd) bounds over created_at; '' disables. */
  dateFrom: string;
  dateTo: string;
  /** Instant search over name, tags and kind. */
  search: string;
};

export const EMPTY_LIBRARY_FILTERS: LibraryFilters = {
  kind: '',
  project: '',
  persona: '',
  provider: '',
  minScore: 0,
  dateFrom: '',
  dateTo: '',
  search: '',
};

export function filtersAreActive(filters: LibraryFilters): boolean {
  return (
    filters.kind !== '' ||
    filters.project !== '' ||
    filters.persona !== '' ||
    filters.provider !== '' ||
    filters.minScore > 0 ||
    filters.dateFrom !== '' ||
    filters.dateTo !== '' ||
    filters.search.trim() !== ''
  );
}

export function filterLibrary(items: readonly LibraryAsset[], filters: LibraryFilters): LibraryAsset[] {
  return items.filter(item => matchesLibraryFilters(item, filters));
}

export function matchesLibraryFilters(item: LibraryAsset, filters: LibraryFilters): boolean {
  if (filters.kind && item.kind !== filters.kind) return false;
  if (filters.project && (item.project ?? '').toLowerCase() !== filters.project.toLowerCase()) return false;
  if (filters.persona && (item.persona ?? '').toLowerCase() !== filters.persona.toLowerCase()) return false;
  if (filters.provider && (item.provider ?? '').toLowerCase() !== filters.provider.toLowerCase()) return false;
  if (filters.minScore > 0 && (item.quality_score == null || item.quality_score < filters.minScore)) return false;
  const createdDay = item.created_at.slice(0, 10);
  if (filters.dateFrom && createdDay < filters.dateFrom) return false;
  if (filters.dateTo && createdDay > filters.dateTo) return false;
  if (filters.search.trim()) {
    const needle = filters.search.trim().toLowerCase();
    const haystack = [item.name, item.kind, ...(item.tags ?? [])].join(' ').toLowerCase();
    if (!haystack.includes(needle)) return false;
  }
  return true;
}

/** The distinct filter options a library offers, sorted for stable rendering. */
export type LibraryFacets = {
  projects: string[];
  personas: string[];
  providers: string[];
};

export function collectFacets(items: readonly LibraryAsset[]): LibraryFacets {
  const collect = (pick: (item: LibraryAsset) => string | null | undefined) =>
    Array.from(new Set(items.map(item => pick(item) ?? '').filter(value => value.trim() !== ''))).sort((a, b) =>
      a.localeCompare(b),
    );
  return {
    projects: collect(item => item.project),
    personas: collect(item => item.persona),
    providers: collect(item => item.provider),
  };
}

export type LibraryCounts = { all: number; image: number; video: number };

export function countLibrary(items: readonly LibraryAsset[]): LibraryCounts {
  return {
    all: items.length,
    image: items.filter(item => item.kind === 'image').length,
    video: items.filter(item => item.kind === 'video').length,
  };
}

// ---------------------------------------------------------------------------
// ETAPA 3 — presentation helpers (unknown → em dash, never an invention)
// ---------------------------------------------------------------------------

export const UNKNOWN_LABEL = '—';

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes) || bytes < 0) return UNKNOWN_LABEL;
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'] as const;
  let value = bytes;
  let unit = 'B';
  for (const next of units) {
    if (value < 1024) break;
    value /= 1024;
    unit = next;
  }
  const rounded = value >= 100 ? String(Math.round(value)) : value.toFixed(1);
  return `${rounded} ${unit}`;
}

export function formatSpeed(bytesPerSecond: number | null | undefined): string {
  if (bytesPerSecond == null || !Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) return UNKNOWN_LABEL;
  return `${formatBytes(bytesPerSecond)}/s`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return UNKNOWN_LABEL;
  const whole = Math.round(seconds);
  const minutes = Math.floor(whole / 60);
  const rest = whole % 60;
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
}

export function formatLibraryDate(iso: string | null | undefined): string {
  if (!iso) return UNKNOWN_LABEL;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return UNKNOWN_LABEL;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export function resolutionLabel(asset: Pick<LibraryAsset, 'resolution' | 'width' | 'height'>): string {
  if (asset.resolution) return asset.resolution;
  if (asset.width && asset.height) return `${asset.width}×${asset.height}`;
  return UNKNOWN_LABEL;
}

// ---------------------------------------------------------------------------
// Quality badges — the bands of the Quality Engine (quality_rules.py):
// < 70 retry · 70–84 manual review · 85–94 approved · ≥ 95 masterpiece
// ---------------------------------------------------------------------------

export type ScoreBand = 'retry' | 'review' | 'approved' | 'masterpiece' | 'unscored';

export function scoreBand(score: number | null | undefined): ScoreBand {
  if (score == null) return 'unscored';
  if (score < 70) return 'retry';
  if (score < 85) return 'review';
  if (score < 95) return 'approved';
  return 'masterpiece';
}

export const SCORE_BAND_LABELS: Record<ScoreBand, string> = {
  retry: 'Retry',
  review: 'Review',
  approved: 'Approved',
  masterpiece: 'Masterpiece',
  unscored: 'Unscored',
};

/** The score floor options the filter bar offers (0 = any score). */
export const SCORE_FLOOR_OPTIONS: ReadonlyArray<{ value: number; label: string }> = [
  { value: 0, label: 'Any score' },
  { value: 70, label: '70+' },
  { value: 85, label: '85+' },
  { value: 95, label: '95+' },
];
