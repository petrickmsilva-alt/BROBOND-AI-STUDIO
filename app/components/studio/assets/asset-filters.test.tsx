// @vitest-environment jsdom
/**
 * PR013 — V4.0.1 · ETAPA 5 — the filter bar.
 *
 * Fully controlled: each control must propagate exactly one patch into the
 * parent's `LibraryFilters`, and the bar must reflect whatever state it is
 * handed (pressed tabs, clear-visibility, live result counts).
 */
import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  EMPTY_LIBRARY_FILTERS,
  type LibraryFilters,
} from '../../../../lib/assets/library';
import { AssetFilterBar } from './asset-filters';

const FACETS = {
  projects: ['Brobond', 'Nocturne'],
  personas: ['Ayla', 'Rin'],
  providers: ['flux', 'wan'],
};

function BarHarness({ initial = EMPTY_LIBRARY_FILTERS }: { initial?: LibraryFilters }) {
  const [filters, setFilters] = useState<LibraryFilters>(initial);
  return (
    <>
      <AssetFilterBar filters={filters} onChange={setFilters} facets={FACETS} resultCount={1} totalCount={4} />
      <output data-testid="mirror">{JSON.stringify(filters)}</output>
    </>
  );
}

function mirror(): LibraryFilters {
  return JSON.parse(screen.getByTestId('mirror').textContent ?? '{}');
}

describe('AssetFilterBar', () => {
  it('searches instantly on every keystroke and clears with the ×', () => {
    render(<BarHarness />);
    const input = screen.getByLabelText('Search by name or tag');
    fireEvent.change(input, { target: { value: 'neon' } });
    expect(mirror().search).toBe('neon');
    fireEvent.click(screen.getByLabelText('Clear search'));
    expect(mirror().search).toBe('');
  });

  it('switches kinds through the pressed tabs', () => {
    render(<BarHarness />);
    const images = screen.getByRole('button', { name: 'Images' });
    const all = screen.getByRole('button', { name: 'All types' });
    expect(all).toHaveAttribute('aria-pressed', 'true');
    expect(images).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(images);
    expect(mirror().kind).toBe('image');
    expect(images).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Videos' }));
    expect(mirror().kind).toBe('video');
  });

  it('offers the real facets and patches each dimension', () => {
    render(<BarHarness />);
    const project = screen.getByLabelText('Filter by project');
    expect(screen.getAllByRole('option').map(option => option.textContent)).toContain('Nocturne');
    fireEvent.change(project, { target: { value: 'Nocturne' } });
    expect(mirror().project).toBe('Nocturne');
    fireEvent.change(screen.getByLabelText('Filter by persona'), { target: { value: 'Rin' } });
    expect(mirror().persona).toBe('Rin');
    fireEvent.change(screen.getByLabelText('Filter by provider'), { target: { value: 'wan' } });
    expect(mirror().provider).toBe('wan');
    fireEvent.change(project, { target: { value: '' } });
    expect(mirror().project).toBe('');
  });

  it('sets the score floor from the Quality Engine bands', () => {
    render(<BarHarness />);
    fireEvent.click(screen.getByRole('button', { name: '85+' }));
    expect(mirror().minScore).toBe(85);
    fireEvent.click(screen.getByRole('button', { name: 'Any score' }));
    expect(mirror().minScore).toBe(0);
  });

  it('bounds the date range', () => {
    render(<BarHarness />);
    fireEvent.change(screen.getByLabelText('From date'), { target: { value: '2026-08-01' } });
    expect(mirror().dateFrom).toBe('2026-08-01');
    fireEvent.change(screen.getByLabelText('To date'), { target: { value: '2026-08-31' } });
    expect(mirror().dateTo).toBe('2026-08-31');
  });

  it('shows Clear only when something is active, and resets everything with it', () => {
    render(<BarHarness />);
    expect(screen.queryByRole('button', { name: 'Clear' })).toBeNull();
    fireEvent.change(screen.getByLabelText('Search by name or tag'), { target: { value: 'neon' } });
    fireEvent.change(screen.getByLabelText('Filter by project'), { target: { value: 'Brobond' } });
    const clear = screen.getByRole('button', { name: 'Clear' });
    fireEvent.click(clear);
    expect(mirror()).toEqual(EMPTY_LIBRARY_FILTERS);
    expect(screen.queryByRole('button', { name: 'Clear' })).toBeNull();
  });

  it('announces filtered vs full counts', () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <AssetFilterBar filters={EMPTY_LIBRARY_FILTERS} onChange={onChange} facets={FACETS} resultCount={4} totalCount={4} />,
    );
    expect(screen.getByText('4 assets')).toBeInTheDocument();
    rerender(<AssetFilterBar filters={EMPTY_LIBRARY_FILTERS} onChange={onChange} facets={FACETS} resultCount={1} totalCount={4} />);
    expect(screen.getByText('1 of 4')).toBeInTheDocument();
  });
});
