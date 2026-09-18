// @vitest-environment jsdom
/**
 * PR013 — V4.0.1 · ETAPA 6 — the five cinematic empty states.
 *
 * Each state exists because the sprint names it; each must use the Design
 * System grammar (eyebrow + title + body) and tell the truth: the offline
 * state says the API did not answer, it never claims the API is down.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AssetEmptyState, STATE_COPY } from './asset-empty';

describe('AssetEmptyState', () => {
  it('exposes exactly the five states the sprint asks for', () => {
    expect(Object.keys(STATE_COPY).sort()).toEqual(['empty', 'error', 'filtered', 'offline', 'uploading']);
  });

  it('renders the empty library with its drop hint', () => {
    render(<AssetEmptyState state="empty" />);
    expect(screen.getByTestId('al-empty-empty')).toHaveAttribute('role', 'status');
    expect(screen.getByText('Nothing on the shelf yet.')).toBeInTheDocument();
    expect(screen.getByText(/PNG, JPG, WEBP, MP4 or MOV/)).toBeInTheDocument();
  });

  it('renders the uploading state while ingest runs', () => {
    render(<AssetEmptyState state="uploading" />);
    expect(screen.getByText('Receiving your material…')).toBeInTheDocument();
    expect(screen.getByText(/every real percentage/)).toBeInTheDocument();
  });

  it('announces errors assertively and quotes the server text verbatim', () => {
    render(<AssetEmptyState state="error" detail="API answered 500" />);
    expect(screen.getByTestId('al-empty-error')).toHaveAttribute('role', 'alert');
    expect(screen.getByText('API answered 500')).toBeInTheDocument();
  });

  it('states no-answer without ever claiming the API is down', () => {
    render(<AssetEmptyState state="offline" />);
    expect(screen.getByTestId('al-empty-offline')).toHaveAttribute('role', 'alert');
    expect(screen.getByText('The studio cannot reach the API.')).toBeInTheDocument();
    expect(screen.getByText(/No answer arrived/)).toBeInTheDocument();
    expect(screen.queryByText(/down/i)).toBeNull();
  });

  it('owns the filtered-everything case under FILTERS', () => {
    render(<AssetEmptyState state="filtered" />);
    expect(screen.getByText('No asset matches this cut.')).toBeInTheDocument();
    expect(screen.getByText('FILTERS')).toBeInTheDocument();
  });

  it('runs the action only when both label and handler exist', () => {
    const onAction = vi.fn();
    const { rerender } = render(<AssetEmptyState state="offline" actionLabel="Try again" onAction={onAction} />);
    fireEvent.click(screen.getByRole('button', { name: /Try again/ }));
    expect(onAction).toHaveBeenCalledTimes(1);

    rerender(<AssetEmptyState state="offline" actionLabel="Try again" />);
    expect(screen.queryByRole('button')).toBeNull();
  });
});
