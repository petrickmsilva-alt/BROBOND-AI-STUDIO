'use client';

/**
 * PR009.7 — Biblioteca Criativa: arrastar e soltar + fila de upload.
 *
 * A área inteira aceita arquivos (contador de profundidade para os limites
 * dos filhos não piscarem o overlay). A fila imprime nome, percentual,
 * velocidade e barra de progresso — valores reais do XHR, nunca simulados.
 * O endpoint é o que já existia: POST /api/v1/assets/upload (via
 * `uploadLibraryAsset`). Nada aqui muda o backend.
 */
import { useRef, useState } from 'react';
import { AlertTriangle, Check, Clapperboard, FileImage, Loader2, Timer, UploadCloud } from 'lucide-react';
import { BIBLIOTECA_COPY } from '../../../../lib/assets/biblioteca';
import { UNKNOWN_LABEL, formatBytes, formatSpeed, type UploadItem } from '../../../../lib/assets/library';

const STATUS_LABELS: Record<UploadItem['status'], string> = {
  queued: 'Na fila',
  uploading: 'Enviando',
  completed: 'Concluído',
  failed: 'Falhou',
};

const STATUS_ICONS: Record<UploadItem['status'], React.ReactNode> = {
  queued: <Timer size={13} aria-hidden="true" />,
  uploading: <Loader2 size={13} className="bib-spin" aria-hidden="true" />,
  completed: <Check size={13} aria-hidden="true" />,
  failed: <AlertTriangle size={13} aria-hidden="true" />,
};

export function BibliotecaDropZone({
  onFiles,
  children,
}: {
  onFiles: (files: File[]) => void;
  children: React.ReactNode;
}) {
  const [dragging, setDragging] = useState(false);
  const depth = useRef(0);

  return (
    <div
      className={`bib-dropzone ${dragging ? 'is-dragging' : ''}`}
      data-testid="bib-dropzone"
      onDragEnter={event => {
        event.preventDefault();
        depth.current += 1;
        if (event.dataTransfer.types.includes('Files')) setDragging(true);
      }}
      onDragOver={event => {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'copy';
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
        const files = Array.from(event.dataTransfer.files);
        if (files.length) onFiles(files);
      }}
    >
      {children}
      {dragging && (
        <div className="bib-drop-overlay" role="status" data-testid="bib-drop-overlay">
          <div className="bib-drop-card">
            <UploadCloud size={26} aria-hidden="true" />
            <strong>{BIBLIOTECA_COPY.dropHint}</strong>
            <span>PNG · JPG · WEBP · MP4 · MOV</span>
          </div>
        </div>
      )}
    </div>
  );
}

/** A área pontilhada permanente — o convite, mesmo sem arrastar nada. */
export function BibliotecaDropHint({ onFiles }: { onFiles: (files: File[]) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <div className="bib-drop-hint" data-testid="bib-drop-hint">
      <UploadCloud size={18} aria-hidden="true" />
      <p>{BIBLIOTECA_COPY.dropHint}</p>
      <button type="button" onClick={() => inputRef.current?.click()}>
        Selecionar arquivos
      </button>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".png,.jpg,.jpeg,.webp,.mp4,.mov"
        className="bib-file-input"
        aria-label="Selecionar arquivos para a Biblioteca"
        onChange={event => {
          if (event.target.files?.length) onFiles(Array.from(event.target.files));
          event.target.value = '';
        }}
      />
    </div>
  );
}

export function BibliotecaUploadQueue({ items }: { items: readonly UploadItem[] }) {
  if (!items.length) return null;
  return (
    <ul className="bib-queue" aria-label="Fila de upload">
      {items.map(item => (
        <li key={item.id} className={`bib-queue-item is-${item.status}`} data-testid={`bib-upload-${item.status}`}>
          <span className="bib-queue-icon" aria-hidden="true">
            {item.kind === 'video' ? <Clapperboard size={15} /> : <FileImage size={15} />}
          </span>
          <span className="bib-queue-copy">
            <span className="bib-queue-row">
              <strong>{item.name}</strong>
              <em className={`bib-queue-status is-${item.status}`}>
                {STATUS_ICONS[item.status]}
                {STATUS_LABELS[item.status]}
              </em>
            </span>
            <span className="bib-queue-row bib-queue-meta">
              <span>{formatBytes(item.size)}</span>
              <span aria-label="progresso">{item.percent}%</span>
              <span>{item.status === 'uploading' ? formatSpeed(item.bytesPerSecond) : UNKNOWN_LABEL}</span>
            </span>
            <span
              className="bib-queue-bar"
              role="progressbar"
              aria-valuenow={item.percent}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`Progresso de ${item.name}`}
            >
              <i style={{ width: `${item.percent}%` }} />
            </span>
            {item.error && <span className="bib-queue-error">{item.error}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}
