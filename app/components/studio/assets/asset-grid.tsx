'use client';

/**
 * PR013 (V4.0.1 · ETAPA 3) — the responsive library grid.
 *
 * Each card shows exactly what the sprint asks: thumbnail, type, project,
 * persona, provider, seed, resolution, quality score and date. Thumbnails
 * are the real stored derivatives (or the image itself); videos and
 * metadata-less legacy rows render an honest kind tile — a fabricated
 * poster frame is worse than an honest icon (the same rule the backend
 * keeps for ffmpeg-less posters).
 */
import { Clapperboard, Film, Play } from 'lucide-react';
import {
  SCORE_BAND_LABELS,
  UNKNOWN_LABEL,
  formatLibraryDate,
  resolutionLabel,
  scoreBand,
  type LibraryAsset,
} from '../../../../lib/assets/library';

export type AssetCardProps = {
  asset: LibraryAsset;
  onOpen: (asset: LibraryAsset) => void;
};

/** The thumbnail source: stored derivative first, the image itself second. */
export function thumbnailSrc(asset: LibraryAsset): string | null {
  if (asset.thumbnail_url) return asset.thumbnail_url;
  if (asset.kind === 'image' && asset.url) return asset.url;
  return null;
}

export function AssetCard({ asset, onOpen }: AssetCardProps) {
  const thumb = thumbnailSrc(asset);
  const band = scoreBand(asset.quality_score);
  return (
    <button
      type="button"
      className="al-card"
      data-testid={`al-card-${asset.id}`}
      onClick={() => onOpen(asset)}
      aria-label={`Open ${asset.name}`}
    >
      <span className="al-card-media">
        {thumb ? (
          // Thumbnails come from the same origin/proxy as the document.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={thumb} alt="" loading="lazy" />
        ) : (
          <span className="al-card-tile" aria-hidden="true">
            {asset.kind === 'video' ? <Film size={22} /> : <Clapperboard size={22} />}
          </span>
        )}
        <span className="al-card-kind">{asset.kind.toUpperCase()}</span>
        {asset.kind === 'video' && (
          <span className="al-card-play" aria-hidden="true">
            <Play size={13} fill="currentColor" />
          </span>
        )}
        <span className={`al-card-score al-score-${band}`} data-band={band}>
          {asset.quality_score == null ? 'Unscored' : `${asset.quality_score} · ${SCORE_BAND_LABELS[band]}`}
        </span>
      </span>
      <span className="al-card-copy">
        <span className="al-card-title">
          <strong>{asset.name}</strong>
          <span className="al-card-res">{resolutionLabel(asset)}</span>
        </span>
        <span className="al-card-meta">
          <Meta label="Project" value={asset.project} />
          <Meta label="Persona" value={asset.persona} />
          <Meta label="Provider" value={asset.provider} />
          <Meta label="Seed" value={asset.seed == null ? null : String(asset.seed)} mono />
        </span>
        <span className="al-card-foot">
          <time dateTime={asset.created_at}>{formatLibraryDate(asset.created_at)}</time>
          {!!asset.tags?.length && <span className="al-card-tags">{asset.tags.slice(0, 2).join(' · ')}</span>}
        </span>
      </span>
    </button>
  );
}

function Meta({ label, value, mono = false }: { label: string; value: string | null | undefined; mono?: boolean }) {
  return (
    <span className={`al-meta ${mono ? 'al-mono' : ''}`}>
      <span>{label}</span>
      <span>{value || UNKNOWN_LABEL}</span>
    </span>
  );
}

export function AssetGrid({ assets, onOpen }: { assets: readonly LibraryAsset[]; onOpen: (asset: LibraryAsset) => void }) {
  if (!assets.length) return null;
  return (
    <div className="al-grid" data-testid="al-grid">
      {assets.map(asset => (
        <AssetCard key={asset.id} asset={asset} onOpen={onOpen} />
      ))}
    </div>
  );
}
