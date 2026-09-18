'use client';

/**
 * PR013 (V4.0.1 · ETAPA 1) — the Upload Engine's drop surface and queue.
 *
 * Two pieces, deliberately split:
 *
 * `AssetDropZone`    — the whole library region is the drop target ("área
 *                      inteira"): drag events are tracked with a depth
 *                      counter so child boundaries never flicker the
 *                      overlay, and the same surface is a labelled button
 *                      for click-to-select. It never looks inside the
 *                      files — `onFiles` decides (the accept-list lives in
 *                      `lib/assets/library.ts`).
 * `UploadQueueList`  — renders every queue item exactly as the spec asks:
 *                      percentage, speed, size and status
 *                      (queued/uploading/completed/failed), with a small
 *                      progress bar. All values come from the upload state
 *                      machine; nothing is simulated.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  Check,
  Clapperboard,
  FileImage,
  Loader2,
  Pause,
  UploadCloud,
} from 'lucide-react';
import {
  UPLOAD_ACCEPT_ATTR,
  UNKNOWN_LABEL,
  formatBytes,
  formatSpeed,
  type UploadItem,
} from '../../../../lib/assets/library';

export type AssetDropZoneProps = {
  onFiles: (files: File[]) => void;
  children: React.ReactNode;
  disabled?: boolean;
};

const STATUS_LABELS: Record<UploadItem['status'], string> = {
  queued: 'Queued',
  uploading: 'Uploading',
  completed: 'Completed',
  failed: 'Failed',
};

export function AssetDropZone({ onFiles, children, disabled = false }: AssetDropZoneProps) {
  const [dragging, setDragging] = useState(false);
  const depth = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const emit = (list: FileList | null) => {
    if (!list || disabled) return;
    const files = Array.from(list);
    if (files.length) onFiles(files);
  };

  return (
    <div
      className={`al-dropzone ${dragging ? 'al-dragging' : ''}`}
      data-testid="al-dropzone"
      onDragEnter={event => {
        event.preventDefault();
        if (disabled) return;
        depth.current += 1;
        if (event.dataTransfer.types.includes('Files')) setDragging(true);
      }}
      onDragOver={event => {
        event.preventDefault();
        if (!disabled) event.dataTransfer.dropEffect = 'copy';
      }}
      onDragLeave={event => {
        event.preventDefault();
        depth.current = Math.max(depth.current - 1, 0);
        if (depth.current === 0) setDragging(false);
      }}
      onDrop={event => {
        event.preventDefault();
        depth.current = 0;
        setDragging(false);
        emit(event.dataTransfer.files);
      }}
    >
      {children}
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={UPLOAD_ACCEPT_ATTR}
        className="al-file-input"
        aria-label="Select files to upload"
        onChange={event => {
          emit(event.target.files);
          event.target.value = '';
        }}
      />
      {dragging && (
        <div className="al-drop-overlay" role="status" data-testid="al-drop-overlay">
          <div className="al-drop-card">
            <UploadCloud size={26} aria-hidden="true" />
            <strong>Drop to add to the library</strong>
            <span>PNG · JPG · WEBP · MP4 · MOV</span>
          </div>
        </div>
      )}
    </div>
  );
}

/** The browse affordance that opens the hidden input of the drop zone. */
export function AssetBrowseButton({ onFiles, label = 'Upload files' }: { onFiles: (files: File[]) => void; label?: string }) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <button type="button" className="primary-button" onClick={() => inputRef.current?.click()}>
      <UploadCloud size={16} aria-hidden="true" /> {label}
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={UPLOAD_ACCEPT_ATTR}
        className="al-file-input"
        aria-label="Select files to upload"
        onChange={event => {
          if (event.target.files?.length) onFiles(Array.from(event.target.files));
          event.target.value = '';
        }}
      />
    </button>
  );
}

const statusIcons: Record<UploadItem['status'], React.ReactNode> = {
  queued: <Pause size={13} aria-hidden="true" />,
  uploading: <Loader2 size={13} className="al-spin" aria-hidden="true" />,
  completed: <Check size={13} aria-hidden="true" />,
  failed: <AlertTriangle size={13} aria-hidden="true" />,
};

export function UploadQueueList({ items }: { items: readonly UploadItem[] }) {
  if (!items.length) return null;
  return (
    <ul className="al-upload-queue" aria-label="Upload queue">
      {items.map(item => (
        <li key={item.id} className={`al-upload-item al-upload-${item.status}`} data-testid={`upload-item-${item.status}`}>
          <span className="al-upload-icon" aria-hidden="true">
            {item.kind === 'video' ? <Clapperboard size={15} /> : <FileImage size={15} />}
          </span>
          <span className="al-upload-copy">
            <span className="al-upload-row">
              <strong>{item.name}</strong>
              <em className={`al-status al-status-${item.status}`}>{statusIcons[item.status]}{STATUS_LABELS[item.status]}</em>
            </span>
            <span className="al-upload-row al-upload-meta">
              <span>{formatBytes(item.size)}</span>
              <span aria-label="progress">{item.percent}%</span>
              <span>{item.status === 'uploading' ? formatSpeed(item.bytesPerSecond) : UNKNOWN_LABEL}</span>
            </span>
            <span
              className="al-progress"
              role="progressbar"
              aria-valuenow={item.percent}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <i style={{ width: `${item.percent}%` }} />
            </span>
            {item.error && <span className="al-upload-error">{item.error}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}
