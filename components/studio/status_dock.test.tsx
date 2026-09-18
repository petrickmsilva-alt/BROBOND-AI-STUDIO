// @vitest-environment jsdom
//
// PR012 — Status Dock: six indicators (API, Database, Storage, GPU, FLUX,
// WAN), dynamic color per state, never taller than 52px, replaces the old
// sidebar Readiness list.

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { StatusDock, type StatusDockIndicator } from './status-dock';
import { indicatorColor, layout } from '../../lib/theme/tokens';

const indicators: StatusDockIndicator[] = [
  { id: 'api', label: 'API', state: 'online' },
  { id: 'database', label: 'Database', state: 'online' },
  { id: 'storage', label: 'Storage', state: 'degraded' },
  { id: 'gpu', label: 'GPU', state: 'online', detail: 'RTX 4090 ready' },
  { id: 'flux', label: 'FLUX', state: 'offline' },
  { id: 'wan', label: 'WAN', state: 'unknown' },
];

describe('StatusDock', () => {
  it('renders exactly the six required indicators, in order', () => {
    render(<StatusDock indicators={indicators} />);
    const items = screen.getAllByText(/API|Database|Storage|GPU|FLUX|WAN/, { selector: '.bb-status-dock-label' });
    expect(items.map(el => el.textContent)).toEqual(['API', 'Database', 'Storage', 'GPU', 'FLUX', 'WAN']);
  });

  it('never exceeds 52px in height', () => {
    render(<StatusDock indicators={indicators} />);
    const dock = screen.getByRole('status', { name: 'System status' });
    expect(dock.style.height).toBe(`${layout.statusDockHeight}px`);
    expect(dock.style.maxHeight).toBe(`${layout.statusDockHeight}px`);
    expect(layout.statusDockHeight).toBeLessThanOrEqual(52);
  });

  it('colors each dot dynamically from its indicator state', () => {
    render(<StatusDock indicators={indicators} />);
    // jsdom normalizes inline hex colors to rgb() — compare through a
    // throwaway element so the assertion is robust to that normalization.
    const toRgb = (hex: string) => {
      const probe = document.createElement('span');
      probe.style.background = hex;
      return probe.style.background;
    };
    const gpuDot = screen.getByText('GPU').previousSibling as HTMLElement;
    expect(gpuDot.style.background).toBe(toRgb(indicatorColor.online));
    const fluxDot = screen.getByText('FLUX').previousSibling as HTMLElement;
    expect(fluxDot.style.background).toBe(toRgb(indicatorColor.offline));
    const storageDot = screen.getByText('Storage').previousSibling as HTMLElement;
    expect(storageDot.style.background).toBe(toRgb(indicatorColor.degraded));
    const wanDot = screen.getByText('WAN').previousSibling as HTMLElement;
    expect(wanDot.style.background).toBe(toRgb(indicatorColor.unknown));
  });

  it('exposes the state as an accessible (visually hidden) text node', () => {
    render(<StatusDock indicators={indicators} />);
    expect(screen.getByText('offline')).toHaveClass('bb-visually-hidden');
  });

  it('uses the detail text as the title attribute when provided, otherwise a generated one', () => {
    render(<StatusDock indicators={indicators} />);
    const gpuItem = screen.getByText('GPU').closest('li');
    expect(gpuItem).toHaveAttribute('title', 'RTX 4090 ready');
    const apiItem = screen.getByText('API').closest('li');
    expect(apiItem).toHaveAttribute('title', 'API: online');
  });

  it('renders an empty dock without crashing when given no indicators', () => {
    render(<StatusDock indicators={[]} />);
    expect(screen.getByRole('status', { name: 'System status' })).toBeInTheDocument();
  });
});
