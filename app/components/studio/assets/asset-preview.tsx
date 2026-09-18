'use client';

/**
 * PR013 (V4.0.1 · ETAPA 4) — the preview surface.
 *
 * Images open in a lightbox with zoom and — when the entry carries a
 * `before_url` — a prepared Before/After comparison slider (the pairing is
 * minted at upload time through `before_asset_id`; the control only shows
 * when the pair is real). Videos get a player with a real timeline (seek
 * included), loop toggle and a download action. Everything read here is
 * the stored file itself; nothing is restaged.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Columns2,
  Download,
  Minus,
  Pause,
  Play,
  Plus,
  Repeat,
  X,
} from 'lucide-react';
import {
  SCORE_BAND_LABELS,
  UNKNOWN_LABEL,
  formatBytes,
  formatDuration,
  formatLibraryDate,
  resolutionLabel,
  scoreBand,
  type LibraryAsset,
} from '../../../../lib/assets/library';

export type AssetPreviewDialogProps = {
  asset: LibraryAsset;
  onClose: () => void;
};

const ZOOM_STEPS: readonly number[] = [1, 1.5, 2, 3, 4];
const ZOOM_DEFAULT_INDEX = 0;

export function AssetPreviewDialog({ asset, onClose }: AssetPreviewDialogProps) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="al-lightbox" role="dialog" aria-modal="true" aria-label={`Preview of ${asset.name}`} data-testid="al-lightbox">
      <button type="button" className="al-lightbox-backdrop" aria-label="Close preview" onClick={onClose} />
      <div className="al-lightbox-panel">
        <header className="al-lightbox-head">
          <div>
            <strong>{asset.name}</strong>
            <span>
              {asset.kind.toUpperCase()} · {resolutionLabel(asset)} · {formatLibraryDate(asset.created_at)}
            </span>
          </div>
          <button type="button" className="al-icon-button" aria-label="Close preview" onClick={onClose}>
            <X size={16} />
          </button>
        </header>
        <div className="al-lightbox-body">
          {asset.kind === 'video' ? <VideoPreview asset={asset} /> : <ImagePreview asset={asset} />}
          <PreviewMetadata asset={asset} />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Image: lightbox + zoom + prepared Before/After
// ---------------------------------------------------------------------------

function ImagePreview({ asset }: { asset: LibraryAsset }) {
  const [zoomIndex, setZoomIndex] = useState(ZOOM_DEFAULT_INDEX);
  const [compare, setCompare] = useState(50);
  const [showCompare, setShowCompare] = useState(true);
  const zoom = ZOOM_STEPS[zoomIndex];
  const beforeUrl = asset.before_url;

  const zoomIn = useCallback(
    () => setZoomIndex(current => Math.min(current + 1, ZOOM_STEPS.length - 1)),
    [],
  );
  const zoomOut = useCallback(
    () => setZoomIndex(current => Math.max(current - 1, ZOOM_DEFAULT_INDEX)),
    [],
  );

  return (
    <div className="al-preview-stage" data-testid="al-image-preview">
      <div className="al-lightbox-tools">
        <button type="button" aria-label="Zoom out" onClick={zoomOut} disabled={zoomIndex <= ZOOM_DEFAULT_INDEX}>
          <Minus size={14} />
        </button>
        <span aria-label="zoom level">{Math.round(zoom * 100)}%</span>
        <button type="button" aria-label="Zoom in" onClick={zoomIn} disabled={zoomIndex >= ZOOM_STEPS.length - 1}>
          <Plus size={14} />
        </button>
        <button type="button" className="al-reset" onClick={() => setZoomIndex(ZOOM_DEFAULT_INDEX)} disabled={zoomIndex === ZOOM_DEFAULT_INDEX}>
          Reset
        </button>
        {beforeUrl && (
          <button
            type="button"
            className={showCompare ? 'al-compare-toggle on' : 'al-compare-toggle'}
            aria-pressed={showCompare}
            onClick={() => setShowCompare(value => !value)}
          >
            <Columns2 size={14} /> Before / After
          </button>
        )}
        <a className="al-download" href={asset.url} download={asset.name} aria-label={`Download ${asset.name}`}>
          <Download size={14} /> Download
        </a>
      </div>
      <div className="al-image-stage">
        {beforeUrl && showCompare ? (
          <div className="al-compare" data-testid="al-compare">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img className="al-compare-after" src={asset.url} alt={`After — ${asset.name}`} style={{ transform: `scale(${zoom})` }} />
            <div className="al-compare-before" style={{ clipPath: `inset(0 ${100 - compare}% 0 0)` }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={beforeUrl} alt={`Before — ${asset.name}`} style={{ transform: `scale(${zoom})` }} />
              <span className="al-compare-label al-compare-label-left">Before</span>
            </div>
            <span className="al-compare-label al-compare-label-right">After</span>
            <input
              type="range"
              min={0}
              max={100}
              value={compare}
              aria-label="Before after comparison"
              onChange={event => setCompare(Number(event.target.value))}
            />
          </div>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img className="al-preview-image" src={asset.url} alt={asset.name} style={{ transform: `scale(${zoom})` }} data-testid="al-preview-image" />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Video: player + timeline + loop + download
// ---------------------------------------------------------------------------

function VideoPreview({ asset }: { asset: LibraryAsset }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [loop, setLoop] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  const togglePlay = useCallback(() => {
    // The <video> is mounted unconditionally in this component, so the ref
    // is populated by the time any of its controls can be pressed.
    const video = videoRef.current as HTMLVideoElement;
    if (video.paused) {
      void video.play();
      setPlaying(true);
    } else {
      video.pause();
      setPlaying(false);
    }
  }, []);

  const seek = useCallback((value: number) => {
    // Same mounted-unconditionally reasoning as togglePlay; a range input
    // only ever yields finite numbers.
    const video = videoRef.current as HTMLVideoElement;
    video.currentTime = value;
    setCurrentTime(value);
  }, []);

  return (
    <div className="al-preview-stage" data-testid="al-video-preview">
      <div className="al-video-stage">
        <video
          ref={videoRef}
          src={asset.url}
          loop={loop}
          playsInline
          preload="metadata"
          onTimeUpdate={event => setCurrentTime(event.currentTarget.currentTime)}
          onLoadedMetadata={event => setDuration(event.currentTarget.duration)}
          onEnded={() => setPlaying(false)}
        />
      </div>
      <div className="al-timeline" data-testid="al-timeline">
        <button type="button" aria-label={playing ? 'Pause' : 'Play'} onClick={togglePlay}>
          {playing ? <Pause size={14} /> : <Play size={14} fill="currentColor" />}
        </button>
        <span className="al-time" aria-label="current time">{formatDuration(currentTime)}</span>
        <input
          type="range"
          min={0}
          max={duration > 0 ? duration : 0}
          step={0.01}
          value={Math.min(currentTime, duration || 0)}
          aria-label="Timeline"
          onChange={event => seek(Number(event.target.value))}
        />
        <span className="al-time" aria-label="duration">{duration > 0 ? formatDuration(duration) : UNKNOWN_LABEL}</span>
        <button
          type="button"
          className={loop ? 'al-loop on' : 'al-loop'}
          aria-pressed={loop}
          aria-label="Toggle loop"
          onClick={() => setLoop(value => !value)}
        >
          <Repeat size={14} />
        </button>
        <a className="al-download" href={asset.url} download={asset.name} aria-label={`Download ${asset.name}`}>
          <Download size={14} />
        </a>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// The fact sheet every preview carries (ETAPA 3's fields, complete)
// ---------------------------------------------------------------------------

function PreviewMetadata({ asset }: { asset: LibraryAsset }) {
  const band = scoreBand(asset.quality_score);
  const rows: Array<[string, string]> = [
    ['Type', asset.kind.toUpperCase()],
    ['Project', asset.project || UNKNOWN_LABEL],
    ['Persona', asset.persona || UNKNOWN_LABEL],
    ['Provider', asset.provider || UNKNOWN_LABEL],
    ['Seed', asset.seed == null ? UNKNOWN_LABEL : String(asset.seed)],
    ['Resolution', resolutionLabel(asset)],
    ['Duration', asset.duration_seconds == null ? UNKNOWN_LABEL : formatDuration(asset.duration_seconds)],
    ['Size', formatBytes(asset.size_bytes)],
    ['Quality', asset.quality_score == null ? 'Unscored' : `${asset.quality_score} · ${SCORE_BAND_LABELS[band]}`],
    ['Date', formatLibraryDate(asset.created_at)],
  ];
  return (
    <aside className="al-facts" aria-label="Asset metadata">
      <h3>Facts</h3>
      <dl>
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {!!asset.tags?.length && (
        <div className="al-facts-tags">
          {asset.tags.map(tag => (
            <span key={tag}>{tag}</span>
          ))}
        </div>
      )}
    </aside>
  );
}
