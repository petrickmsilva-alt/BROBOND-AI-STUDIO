// @vitest-environment jsdom
/**
 * PR013 — V4.0.1 · ETAPA 3 — the responsive grid.
 *
 * Every card must show the ten facts the sprint lists (thumbnail, type,
 * project, persona, provider, seed, resolution, score, date) using the
 * real stored data — and render `—` where the metadata is honestly unknown.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { LibraryAsset } from '../../../../lib/assets/library';
import { AssetCard, AssetGrid, thumbnailSrc } from './asset-grid';

function asset(overrides: Partial<LibraryAsset> = {}): LibraryAsset {
  return {
    id: 'a1',
    name: 'Lobby wide v2.png',
    kind: 'image',
    url: '/files/lobby.png',
    created_at: '2026-08-12T11:22:33Z',
    has_metadata: true,
    project: 'Brobond',
    persona: 'Ayla',
    provider: 'flux',
    seed: 421337,
    width: 1920,
    height: 1080,
    resolution: '1920×1080',
    tags: ['neon', 'lobby'],
    quality_score: 96,
    thumbnail_url: '/files/thumbs/lobby.jpg',
    ...overrides,
  };
}

describe('thumbnailSrc', () => {
  it('prefers the stored derivative, falls back to the image itself, never invents', () => {
    expect(thumbnailSrc(asset())).toBe('/files/thumbs/lobby.jpg');
    expect(thumbnailSrc(asset({ thumbnail_url: null }))).toBe('/files/lobby.png');
    expect(thumbnailSrc(asset({ kind: 'video', thumbnail_url: null, url: '/files/take.mp4' }))).toBeNull();
  });
});

describe('AssetCard', () => {
  it('shows the whole fact sheet of the sprint', () => {
    render(<AssetCard asset={asset()} onOpen={() => undefined} />);
    expect(screen.getByAltText('')).toHaveAttribute('src', '/files/thumbs/lobby.jpg');
    expect(screen.getByText('IMAGE')).toBeInTheDocument();
    expect(screen.getByText('Brobond')).toBeInTheDocument();
    expect(screen.getByText('Ayla')).toBeInTheDocument();
    expect(screen.getByText('flux')).toBeInTheDocument();
    expect(screen.getByText('421337')).toBeInTheDocument();
    expect(screen.getByText('1920×1080')).toBeInTheDocument();
    expect(screen.getByText('96 · Masterpiece')).toBeInTheDocument();
    expect(screen.getByText('Aug 12, 2026')).toBeInTheDocument();
    expect(screen.getByText('neon · lobby')).toBeInTheDocument();
  });

  it('bands the score with the Quality Engine colors', () => {
    const { rerender } = render(<AssetCard asset={asset({ quality_score: 60 })} onOpen={() => undefined} />);
    expect(screen.getByText('60 · Retry')).toBeInTheDocument();
    rerender(<AssetCard asset={asset({ quality_score: 72 })} onOpen={() => undefined} />);
    expect(screen.getByText('72 · Review')).toBeInTheDocument();
    rerender(<AssetCard asset={asset({ quality_score: 88 })} onOpen={() => undefined} />);
    expect(screen.getByText('88 · Approved')).toBeInTheDocument();
    rerender(<AssetCard asset={asset({ quality_score: null })} onOpen={() => undefined} />);
    expect(screen.getByText('Unscored')).toBeInTheDocument();
  });

  it('debuts videos with the play emblem and a tile when no poster exists', () => {
    const { container } = render(
      <AssetCard
        asset={asset({ kind: 'video', name: 'Take 07.mp4', thumbnail_url: null, url: '/files/take.mp4' })}
        onOpen={() => undefined}
      />,
    );
    expect(container.querySelector('.al-card-play')).not.toBeNull();
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('VIDEO')).toBeInTheDocument();
  });

  it('renders the image tile for a metadata-less image row', () => {
    const { container } = render(
      <AssetCard asset={asset({ thumbnail_url: null, url: '' })} onOpen={() => undefined} />,
    );
    expect(container.querySelector('.al-card-tile')).not.toBeNull();
    expect(container.querySelector('.al-card-play')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
  });

  it('renders dashes for unknown metadata — never a guess', () => {
    render(
      <AssetCard
        asset={asset({ project: null, persona: null, provider: null, seed: null, width: null, height: null, resolution: null, tags: [] })}
        onOpen={() => undefined}
      />,
    );
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(4);
    expect(screen.queryByText(/neon/)).toBeNull();
  });

  it('opens the preview with the exact asset on click', () => {
    const onOpen = vi.fn();
    const entry = asset();
    render(<AssetCard asset={entry} onOpen={onOpen} />);
    fireEvent.click(screen.getByRole('button', { name: 'Open Lobby wide v2.png' }));
    expect(onOpen).toHaveBeenCalledWith(entry);
  });
});

describe('AssetGrid', () => {
  it('renders every visible asset and nothing when empty', () => {
    const { container, rerender } = render(
      <AssetGrid assets={[asset({ id: 'a' }), asset({ id: 'b', name: 'Take 09.mp4', kind: 'video' })]} onOpen={() => undefined} />,
    );
    expect(container.querySelectorAll('.al-card')).toHaveLength(2);
    rerender(<AssetGrid assets={[]} onOpen={() => undefined} />);
    expect(container.querySelector('.al-grid')).toBeNull();
  });
});
