// @vitest-environment jsdom
/**
 * PR013 — V4.0.1 · ETAPA 4 — the preview surface.
 *
 * Images: lightbox, real zoom steps, and a Before/After slider that only
 * appears when the pair is real (`before_url`). Videos: player, real
 * timeline (seek + time readout), loop toggle, download. Esc/backdrop/×
 * all close it. Nothing is restaged — the URLs are the stored files.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import type { LibraryAsset } from '../../../../lib/assets/library';
import { AssetPreviewDialog } from './asset-preview';

beforeAll(() => {
  // jsdom's media elements are inert; give the suite controllable doubles.
  let paused = true;
  Object.defineProperty(window.HTMLMediaElement.prototype, 'paused', {
    configurable: true,
    get() {
      return paused;
    },
  });
  Object.defineProperty(window.HTMLMediaElement.prototype, 'currentTime', {
    configurable: true,
    writable: true,
    value: 0,
  });
  Object.defineProperty(window.HTMLMediaElement.prototype, 'duration', {
    configurable: true,
    writable: true,
    value: 0,
  });
  window.HTMLMediaElement.prototype.play = function play() {
    paused = false;
    return Promise.resolve();
  };
  window.HTMLMediaElement.prototype.pause = function pause() {
    paused = true;
  };
});

function image(overrides: Partial<LibraryAsset> = {}): LibraryAsset {
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
    size_bytes: 2_097_152,
    duration_seconds: null,
    quality_score: 96,
    tags: ['neon', 'lobby'],
    ...overrides,
  };
}

describe('image preview', () => {
  it('zooms in discrete steps and resets', () => {
    render(<AssetPreviewDialog asset={image()} onClose={() => undefined} />);
    const picture = screen.getByTestId('al-preview-image');
    expect(picture).toHaveStyle({ transform: 'scale(1)' });
    expect(screen.getByText('100%')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Zoom in'));
    expect(screen.getByText('150%')).toBeInTheDocument();
    expect(picture).toHaveStyle({ transform: 'scale(1.5)' });

    fireEvent.click(screen.getByLabelText('Zoom out'));
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByLabelText('Zoom out')).toBeDisabled();

    fireEvent.click(screen.getByLabelText('Zoom in'));
    fireEvent.click(screen.getByLabelText('Zoom in'));
    fireEvent.click(screen.getByLabelText('Zoom in'));
    fireEvent.click(screen.getByLabelText('Zoom in'));
    expect(screen.getByText('400%')).toBeInTheDocument();
    expect(screen.getByLabelText('Zoom in')).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('offers Before / After only when the pair is real', () => {
    render(<AssetPreviewDialog asset={image({ before_url: '/files/lobby-before.png' })} onClose={() => undefined} />);
    expect(screen.getByTestId('al-compare')).toBeInTheDocument();
    expect(screen.getByAltText(/Before —/)).toHaveAttribute('src', '/files/lobby-before.png');
    expect(screen.getByAltText(/After —/)).toHaveAttribute('src', '/files/lobby.png');

    const slider = screen.getByLabelText('Before after comparison');
    fireEvent.change(slider, { target: { value: '80' } });
    const beforePane = document.querySelector('.al-compare-before') as HTMLElement;
    expect(beforePane.style.clipPath).toBe('inset(0 20% 0 0)');

    fireEvent.click(screen.getByRole('button', { name: /Before \/ After/ }));
    expect(screen.queryByTestId('al-compare')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Before \/ After/ }));
    expect(screen.getByTestId('al-compare')).toBeInTheDocument();
  });

  it('hides the comparison control entirely without a before URL', () => {
    render(<AssetPreviewDialog asset={image({ before_url: null })} onClose={() => undefined} />);
    expect(screen.queryByRole('button', { name: /Before \/ After/ })).toBeNull();
    expect(screen.getByTestId('al-preview-image')).toBeInTheDocument();
  });
});

describe('video preview', () => {
  const videoAsset = () =>
    image({ id: 'v1', name: 'Take 07.mp4', kind: 'video', url: '/files/take.mp4', duration_seconds: 65 });

  it('plays, seeks through the timeline and toggles the loop', () => {
    render(<AssetPreviewDialog asset={videoAsset()} onClose={() => undefined} />);
    const stage = screen.getByTestId('al-video-preview');
    const element = stage.querySelector('video') as HTMLVideoElement;
    expect(element).toHaveAttribute('src', '/files/take.mp4');

    fireEvent.click(screen.getByLabelText('Play'));
    expect(screen.getByLabelText('Pause')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Pause'));
    expect(screen.getByLabelText('Play')).toBeInTheDocument();

    element.currentTime = 21.4;
    fireEvent.timeUpdate(element);
    expect(screen.getByLabelText('current time')).toHaveTextContent('00:21');

    Object.defineProperty(element, 'duration', { configurable: true, writable: true, value: 65 });
    fireEvent.loadedMetadata(element);
    expect(screen.getByLabelText('duration')).toHaveTextContent('01:05');

    fireEvent.change(screen.getByLabelText('Timeline'), { target: { value: '40' } });
    expect(element.currentTime).toBe(40);

    const loop = screen.getByLabelText('Toggle loop');
    expect(loop).toHaveAttribute('aria-pressed', 'false');
    expect(element.loop).toBe(false);
    fireEvent.click(loop);
    expect(loop).toHaveAttribute('aria-pressed', 'true');
    expect(element.loop).toBe(true);
  });

  it('marks the end of playback honestly', () => {
    render(<AssetPreviewDialog asset={videoAsset()} onClose={() => undefined} />);
    const element = screen.getByTestId('al-video-preview').querySelector('video') as HTMLVideoElement;
    fireEvent.click(screen.getByLabelText('Play'));
    fireEvent.ended(element);
    expect(screen.getByLabelText('Play')).toBeInTheDocument();
  });

  it('shows the honest dash when the duration never arrives', () => {
    render(<AssetPreviewDialog asset={videoAsset()} onClose={() => undefined} />);
    expect(screen.getByLabelText('duration')).toHaveTextContent('—');
  });
});

describe('the dialog chrome and facts', () => {
  it('closes via Esc, the × and the backdrop', () => {
    const onClose = vi.fn();
    const { rerender } = render(<AssetPreviewDialog asset={image()} onClose={onClose} />);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);

    const [backdrop, close] = screen.getAllByLabelText('Close preview');
    fireEvent.click(close);
    expect(onClose).toHaveBeenCalledTimes(2);

    rerender(<AssetPreviewDialog asset={image()} onClose={onClose} />);
    fireEvent.keyDown(window, { key: 'Enter' });
    expect(onClose).toHaveBeenCalledTimes(2);
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it('prints the complete fact sheet with real values and a download', () => {
    render(<AssetPreviewDialog asset={image()} onClose={() => undefined} />);
    const facts = screen.getByLabelText('Asset metadata');
    expect(facts).toHaveTextContent('Brobond');
    expect(facts).toHaveTextContent('Ayla');
    expect(facts).toHaveTextContent('flux');
    expect(facts).toHaveTextContent('421337');
    expect(facts).toHaveTextContent('1920×1080');
    expect(facts).toHaveTextContent('2.0 MB');
    expect(facts).toHaveTextContent('96 · Masterpiece');
    expect(facts).toHaveTextContent('Aug 12, 2026');
    expect(screen.getByText('neon')).toBeInTheDocument();
    expect(screen.getByText('lobby')).toBeInTheDocument();

    const download = screen.getByLabelText('Download Lobby wide v2.png');
    expect(download).toHaveAttribute('href', '/files/lobby.png');
    expect(download).toHaveAttribute('download', 'Lobby wide v2.png');
  });

  it('keeps dashes for every unknown fact', () => {
    render(
      <AssetPreviewDialog
        asset={image({ project: null, persona: null, provider: null, seed: null, width: null, height: null, resolution: null, size_bytes: null, duration_seconds: null, quality_score: null, tags: [] })}
        onClose={() => undefined}
      />,
    );
    const facts = screen.getByLabelText('Asset metadata');
    expect(facts).toHaveTextContent('Unscored');
    expect(facts.querySelectorAll('dd')).toHaveLength(10);
    expect(Array.from(facts.querySelectorAll('dd')).filter(dd => dd.textContent === '—').length).toBeGreaterThanOrEqual(7);
  });
});
