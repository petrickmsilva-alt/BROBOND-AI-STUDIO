'use client';

/**
 * PR009.7 — Biblioteca Criativa: o preview fullscreen (fade 220ms).
 *
 * Imagem: zoom, download, copiar URL e informações.
 * Vídeo: player, timeline, volume, fullscreen e informações.
 *
 * Nenhum endpoint novo: tudo aqui é o arquivo já armazenado (`asset.url`)
 * e os metadados que a listagem existente já devolve.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Copy,
  Download,
  Info,
  Maximize2,
  Minus,
  Pause,
  Play,
  Plus,
  Volume2,
  VolumeX,
  X,
} from 'lucide-react';
import {
  KIND_BADGE,
  UNKNOWN,
  assetKind,
  displayTags,
  formatClock,
  formatDateBR,
  formatSizeBR,
  qualityBadge,
  resolutionBR,
  type LibraryAsset,
} from '../../../../lib/assets/biblioteca';

const ZOOM_STEPS: readonly number[] = [1, 1.5, 2, 3, 4];

export type BibliotecaPreviewProps = {
  asset: LibraryAsset;
  onClose: () => void;
  onCopyUrl: (asset: LibraryAsset) => void;
  /** Transient confirmation ("URL copiada") owned by the orchestrator. */
  copyNotice?: string;
};

export function BibliotecaPreview({ asset, onClose, onCopyUrl, copyNotice }: BibliotecaPreviewProps) {
  const [showInfo, setShowInfo] = useState(true);
  const kind = assetKind(asset);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="bib-modal" role="dialog" aria-modal="true" aria-label={`Preview de ${asset.name}`} data-testid="bib-modal">
      <button type="button" className="bib-modal-backdrop" aria-label="Fechar preview" onClick={onClose} />
      <div className="bib-modal-panel">
        <header className="bib-modal-head">
          <div>
            <strong>{asset.name}</strong>
            <span>
              {KIND_BADGE[kind]} · {resolutionBR(asset)} · {formatDateBR(asset.created_at)}
            </span>
          </div>
          <div className="bib-modal-head-actions">
            <button
              type="button"
              className={showInfo ? 'bib-ghost is-on' : 'bib-ghost'}
              aria-pressed={showInfo}
              onClick={() => setShowInfo(value => !value)}
            >
              <Info size={14} /> Informações
            </button>
            <button type="button" className="bib-ghost" onClick={() => onCopyUrl(asset)}>
              <Copy size={14} /> Copiar URL
            </button>
            <a className="bib-ghost" href={asset.url} download={asset.name}>
              <Download size={14} /> Download
            </a>
            <button type="button" className="bib-icon" aria-label="Fechar preview" onClick={onClose}>
              <X size={16} />
            </button>
          </div>
        </header>

        {copyNotice && (
          <p className="bib-modal-notice" role="status">
            {copyNotice}
          </p>
        )}

        <div className={showInfo ? 'bib-modal-body' : 'bib-modal-body no-info'}>
          {kind === 'video' || kind === 'audio' ? <MediaStage asset={asset} kind={kind} /> : <ImageStage asset={asset} />}
          {showInfo && <PreviewFacts asset={asset} />}
        </div>
      </div>
    </div>
  );
}

function ImageStage({ asset }: { asset: LibraryAsset }) {
  const [step, setStep] = useState(0);
  const zoom = ZOOM_STEPS[step];
  return (
    <div className="bib-stage" data-testid="bib-stage-image">
      <div className="bib-stage-canvas">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={asset.url} alt={asset.name} style={{ transform: `scale(${zoom})` }} data-testid="bib-preview-image" />
      </div>
      <div className="bib-stage-bar">
        <button type="button" aria-label="Reduzir zoom" onClick={() => setStep(value => Math.max(value - 1, 0))} disabled={step === 0}>
          <Minus size={14} />
        </button>
        <span aria-label="nível de zoom">{Math.round(zoom * 100)}%</span>
        <button
          type="button"
          aria-label="Aumentar zoom"
          onClick={() => setStep(value => Math.min(value + 1, ZOOM_STEPS.length - 1))}
          disabled={step === ZOOM_STEPS.length - 1}
        >
          <Plus size={14} />
        </button>
        <button type="button" onClick={() => setStep(0)} disabled={step === 0}>
          Redefinir
        </button>
      </div>
    </div>
  );
}

function MediaStage({ asset, kind }: { asset: LibraryAsset; kind: 'video' | 'audio' }) {
  const mediaRef = useRef<HTMLVideoElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);

  const togglePlay = useCallback(() => {
    const media = mediaRef.current as HTMLVideoElement;
    if (media.paused) {
      void media.play();
      setPlaying(true);
    } else {
      media.pause();
      setPlaying(false);
    }
  }, []);

  const seek = useCallback((value: number) => {
    const media = mediaRef.current as HTMLVideoElement;
    media.currentTime = value;
    setCurrent(value);
  }, []);

  const changeVolume = useCallback((value: number) => {
    const media = mediaRef.current as HTMLVideoElement;
    media.volume = value;
    media.muted = value === 0;
    setVolume(value);
    setMuted(value === 0);
  }, []);

  const toggleMute = useCallback(() => {
    const media = mediaRef.current as HTMLVideoElement;
    const next = !media.muted;
    media.muted = next;
    setMuted(next);
  }, []);

  const goFullscreen = useCallback(() => {
    const stage = stageRef.current;
    // jsdom and older browsers have no Fullscreen API — the control simply
    // does nothing there rather than throwing at the user.
    if (stage && typeof stage.requestFullscreen === 'function') void stage.requestFullscreen();
  }, []);

  return (
    <div className="bib-stage" data-testid="bib-stage-video">
      <div className="bib-stage-canvas bib-stage-video" ref={stageRef}>
        <video
          ref={mediaRef}
          src={asset.url}
          playsInline
          preload="metadata"
          poster={kind === 'video' ? asset.thumbnail_url ?? undefined : undefined}
          onTimeUpdate={event => setCurrent(event.currentTarget.currentTime)}
          onLoadedMetadata={event => setDuration(event.currentTarget.duration)}
          onEnded={() => setPlaying(false)}
        />
      </div>
      <div className="bib-stage-bar" data-testid="bib-timeline">
        <button type="button" aria-label={playing ? 'Pausar' : 'Reproduzir'} onClick={togglePlay}>
          {playing ? <Pause size={14} /> : <Play size={14} fill="currentColor" />}
        </button>
        <span className="bib-time">{formatClock(current)}</span>
        <input
          type="range"
          className="bib-range"
          min={0}
          max={duration > 0 ? duration : 0}
          step={0.01}
          value={Math.min(current, duration || 0)}
          aria-label="Linha do tempo"
          onChange={event => seek(Number(event.target.value))}
        />
        <span className="bib-time">{duration > 0 ? formatClock(duration) : UNKNOWN}</span>
        <button type="button" aria-label={muted ? 'Ativar som' : 'Silenciar'} onClick={toggleMute}>
          {muted ? <VolumeX size={14} /> : <Volume2 size={14} />}
        </button>
        <input
          type="range"
          className="bib-range bib-range-volume"
          min={0}
          max={1}
          step={0.05}
          value={muted ? 0 : volume}
          aria-label="Volume"
          onChange={event => changeVolume(Number(event.target.value))}
        />
        <button type="button" aria-label="Tela cheia" onClick={goFullscreen}>
          <Maximize2 size={14} />
        </button>
      </div>
    </div>
  );
}

function PreviewFacts({ asset }: { asset: LibraryAsset }) {
  const kind = assetKind(asset);
  const quality = qualityBadge(asset);
  const tags = displayTags(asset, 8);
  const rows: Array<[string, string]> = [
    ['Tipo', KIND_BADGE[kind]],
    ['Resolução', resolutionBR(asset)],
    ['Tamanho', formatSizeBR(asset.size_bytes)],
    ['Duração', asset.duration_seconds == null ? UNKNOWN : formatClock(asset.duration_seconds)],
    ['Projeto', asset.project || UNKNOWN],
    ['Persona', asset.persona || UNKNOWN],
    ['Provedor', asset.provider || UNKNOWN],
    ['Seed', asset.seed == null ? UNKNOWN : String(asset.seed)],
    ['Qualidade', quality.label],
    ['Data', formatDateBR(asset.created_at)],
  ];
  return (
    <aside className="bib-facts" aria-label="Informações do arquivo">
      <h2>Informações</h2>
      <dl>
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {tags.length > 0 && (
        <div className="bib-facts-tags">
          {tags.map(tag => (
            <span key={tag}>{tag}</span>
          ))}
        </div>
      )}
    </aside>
  );
}
