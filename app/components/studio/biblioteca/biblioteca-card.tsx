'use client';

/**
 * PR009.7 — Biblioteca Criativa: o card do asset (≈220×250, radius 16).
 *
 * Thumbnail grande + badge de tipo (IMG / VIDEO / AUDIO), rodapé com nome,
 * resolução, data e tamanho, e — no hover — preview, favoritar e o menu
 * (...). Tudo o que ele mostra vem dos metadados já armazenados; o que o
 * backend não sabe aparece como `—`, nunca inventado.
 */
import { useEffect, useRef, useState } from 'react';
import {
  Copy,
  Download,
  Eye,
  Film,
  ImageOff,
  MoreHorizontal,
  Music4,
  Play,
  Star,
} from 'lucide-react';
import {
  KIND_BADGE,
  assetKind,
  displayTags,
  formatDateBR,
  formatSizeBR,
  qualityBadge,
  resolutionBR,
  type LibraryAsset,
} from '../../../../lib/assets/biblioteca';

export type BibliotecaCardProps = {
  asset: LibraryAsset;
  favorite: boolean;
  onOpen: (asset: LibraryAsset) => void;
  onToggleFavorite: (asset: LibraryAsset) => void;
  onCopyUrl: (asset: LibraryAsset) => void;
};

/** Thumbnail: the stored derivative first, the image itself second. */
export function cardThumbnail(asset: LibraryAsset): string | null {
  if (asset.thumbnail_url) return asset.thumbnail_url;
  if (assetKind(asset) === 'image' && asset.url) return asset.url;
  return null;
}

export function BibliotecaCard({ asset, favorite, onOpen, onToggleFavorite, onCopyUrl }: BibliotecaCardProps) {
  const kind = assetKind(asset);
  const thumb = cardThumbnail(asset);
  const quality = qualityBadge(asset);
  const tags = displayTags(asset);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRoot = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const onAway = (event: MouseEvent) => {
      if (menuRoot.current && !menuRoot.current.contains(event.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', onAway);
    return () => document.removeEventListener('mousedown', onAway);
  }, [menuOpen]);

  const KindIcon = kind === 'video' ? Film : kind === 'audio' ? Music4 : ImageOff;

  return (
    <article className="bib-card" data-testid={`bib-card-${asset.id}`} data-kind={kind}>
      <div className="bib-card-media">
        {thumb ? (
          // Same origin/proxy as the document — Next's loader is not involved.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={thumb} alt="" loading="lazy" />
        ) : (
          <span className="bib-card-fallback" aria-hidden="true">
            <KindIcon size={24} />
          </span>
        )}

        <span className="bib-card-kind" data-kind={kind}>
          {KIND_BADGE[kind]}
        </span>
        <span className={`bib-card-quality bib-quality-${quality.id}`}>{quality.label}</span>

        {kind === 'video' && (
          <span className="bib-card-play" aria-hidden="true">
            <Play size={12} fill="currentColor" />
          </span>
        )}

        <div className="bib-card-hover">
          <button type="button" className="bib-hover-action" onClick={() => onOpen(asset)} aria-label={`Visualizar ${asset.name}`}>
            <Eye size={15} />
          </button>
          <button
            type="button"
            className={favorite ? 'bib-hover-action is-favorite' : 'bib-hover-action'}
            aria-pressed={favorite}
            aria-label={favorite ? `Remover ${asset.name} dos favoritos` : `Favoritar ${asset.name}`}
            onClick={() => onToggleFavorite(asset)}
          >
            <Star size={15} fill={favorite ? 'currentColor' : 'none'} />
          </button>
          <div className="bib-card-menu" ref={menuRoot}>
            <button
              type="button"
              className="bib-hover-action"
              aria-label={`Mais opções para ${asset.name}`}
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen(open => !open)}
            >
              <MoreHorizontal size={15} />
            </button>
            {menuOpen && (
              <ul className="bib-menu" role="menu">
                <li>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false);
                      onOpen(asset);
                    }}
                  >
                    <Eye size={13} /> Preview
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false);
                      onCopyUrl(asset);
                    }}
                  >
                    <Copy size={13} /> Copiar URL
                  </button>
                </li>
                <li>
                  <a role="menuitem" href={asset.url} download={asset.name} onClick={() => setMenuOpen(false)}>
                    <Download size={13} /> Download
                  </a>
                </li>
              </ul>
            )}
          </div>
        </div>

        {favorite && (
          <span className="bib-card-starred" aria-hidden="true">
            <Star size={12} fill="currentColor" />
          </span>
        )}

        <button type="button" className="bib-card-open" onClick={() => onOpen(asset)} aria-label={`Abrir ${asset.name}`} />
      </div>

      <div className="bib-card-foot">
        <strong title={asset.name}>{asset.name}</strong>
        <span className="bib-card-line">
          <span>{resolutionBR(asset)}</span>
          <span>{formatSizeBR(asset.size_bytes)}</span>
        </span>
        <span className="bib-card-line bib-card-dim">
          <time dateTime={asset.created_at}>{formatDateBR(asset.created_at)}</time>
          {tags.length > 0 && (
            <span className="bib-card-tags">
              {tags.map(tag => (
                <em key={tag}>{tag}</em>
              ))}
            </span>
          )}
        </span>
      </div>
    </article>
  );
}

export function BibliotecaGrid({
  assets,
  favorites,
  onOpen,
  onToggleFavorite,
  onCopyUrl,
}: {
  assets: readonly LibraryAsset[];
  favorites: ReadonlySet<string>;
  onOpen: (asset: LibraryAsset) => void;
  onToggleFavorite: (asset: LibraryAsset) => void;
  onCopyUrl: (asset: LibraryAsset) => void;
}) {
  if (!assets.length) return null;
  return (
    <div className="bib-grid" data-testid="bib-grid">
      {assets.map(asset => (
        <BibliotecaCard
          key={asset.id}
          asset={asset}
          favorite={favorites.has(asset.id)}
          onOpen={onOpen}
          onToggleFavorite={onToggleFavorite}
          onCopyUrl={onCopyUrl}
        />
      ))}
    </div>
  );
}
