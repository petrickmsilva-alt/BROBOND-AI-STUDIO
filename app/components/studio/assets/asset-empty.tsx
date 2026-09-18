'use client';

/**
 * PR013 (V4.0.1 · ETAPA 6) — the cinematic empty states.
 *
 * Five states, one calm visual grammar from the existing Design System
 * (token colors, dm-mono eyebrow, dashed frame): empty library, upload in
 * progress, error, no connection and "filters ate everything". Copy stays
 * factual — the offline state says the API did not answer, never "the API
 * is down" (V3.2.1's lesson).
 */
import { CloudOff, Library, RefreshCw, ScanSearch, TriangleAlert, UploadCloud } from 'lucide-react';

export type AssetLibraryState = 'empty' | 'uploading' | 'error' | 'offline' | 'filtered';

export const STATE_COPY: Record<
  AssetLibraryState,
  { icon: React.ReactNode; eyebrow: string; title: string; body: string }
> = {
  empty: {
    icon: <Library size={24} aria-hidden="true" />,
    eyebrow: 'THE LIBRARY',
    title: 'Nothing on the shelf yet.',
    body: 'Drag a frame or a take anywhere on this page — PNG, JPG, WEBP, MP4 or MOV — and it becomes part of the archive with its metadata intact.',
  },
  uploading: {
    icon: <UploadCloud size={24} aria-hidden="true" />,
    eyebrow: 'INGEST',
    title: 'Receiving your material…',
    body: 'Files are being written to storage with their thumbnails and metadata. The queue above shows every real percentage.',
  },
  error: {
    icon: <TriangleAlert size={24} aria-hidden="true" />,
    eyebrow: 'SOMETHING BROKE',
    title: 'The library could not be read.',
    body: 'The API answered with an error. Try again — if it persists, the message below is the exact answer the server gave.',
  },
  offline: {
    icon: <CloudOff size={24} aria-hidden="true" />,
    eyebrow: 'NO CONNECTION',
    title: 'The studio cannot reach the API.',
    body: 'No answer arrived from the backend. Check your connection, or start FastAPI locally — your files are safe until then.',
  },
  filtered: {
    icon: <ScanSearch size={24} aria-hidden="true" />,
    eyebrow: 'FILTERS',
    title: 'No asset matches this cut.',
    body: 'Loosen a filter or clear the search — the library itself is intact underneath.',
  },
};

export function AssetEmptyState({
  state,
  detail,
  actionLabel,
  onAction,
}: {
  state: AssetLibraryState;
  detail?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  const copy = STATE_COPY[state];
  return (
    <div className={`al-empty al-empty-${state}`} role={state === 'error' || state === 'offline' ? 'alert' : 'status'} data-testid={`al-empty-${state}`}>
      <span className="al-empty-icon">{copy.icon}</span>
      <span className="al-empty-eyebrow">{copy.eyebrow}</span>
      <h3>{copy.title}</h3>
      <p>{copy.body}</p>
      {detail && <code>{detail}</code>}
      {actionLabel && onAction && (
        <button type="button" className="secondary-button" onClick={onAction}>
          <RefreshCw size={14} aria-hidden="true" /> {actionLabel}
        </button>
      )}
    </div>
  );
}
