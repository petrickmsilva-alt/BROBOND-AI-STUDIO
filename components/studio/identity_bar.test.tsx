// @vitest-environment jsdom
//
// PR012 — Identity Bar: avatar, persona name, style, LoRA, palette and a
// "Ready" status pill, always visible above the Hero Workspace.

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { IdentityBar } from './identity-bar';

describe('IdentityBar', () => {
  it('shows a "no identity" state when there is no persona selected', () => {
    render(<IdentityBar />);
    expect(screen.getByText('No persona selected')).toBeInTheDocument();
    expect(screen.getByText('No identity')).toBeInTheDocument();
  });

  it('renders the persona name, style, LoRA and Ready status when everything is set', () => {
    render(<IdentityBar personaName="BROBOND / 01" style="Cinematic realism" lora="v1.2" status="ready" />);
    expect(screen.getByText('BROBOND / 01')).toBeInTheDocument();
    expect(screen.getByText('Cinematic realism')).toBeInTheDocument();
    expect(screen.getByText('v1.2')).toBeInTheDocument();
    expect(screen.getByText('Ready')).toBeInTheDocument();
  });

  it('renders an avatar image when an avatarUrl is supplied', () => {
    render(<IdentityBar personaName="BROBOND / 01" avatarUrl="https://example.com/a.jpg" />);
    expect(screen.getByAltText('BROBOND / 01 avatar')).toBeInTheDocument();
  });

  it('falls back to a placeholder icon without an avatarUrl', () => {
    const { container } = render(<IdentityBar personaName="BROBOND / 01" />);
    expect(container.querySelector('img')).toBeNull();
  });

  it('shows "None" when no LoRA is selected and a dash when no style is set', () => {
    render(<IdentityBar personaName="BROBOND / 01" />);
    expect(screen.getByText('None')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('renders palette swatches, defaulting to the brand palette when none is given', () => {
    const { container } = render(<IdentityBar personaName="BROBOND / 01" />);
    expect(container.querySelectorAll('.bb-identity-swatch')).toHaveLength(3);
  });

  it('renders a custom palette when provided', () => {
    const { container } = render(<IdentityBar personaName="BROBOND / 01" palette={['#111111', '#222222']} />);
    expect(container.querySelectorAll('.bb-identity-swatch')).toHaveLength(2);
  });

  it('reflects a loading status only when a persona is active', () => {
    render(<IdentityBar personaName="BROBOND / 01" status="loading" />);
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });

  it('ignores an explicit status when there is no persona (always reports no-identity)', () => {
    render(<IdentityBar status="ready" />);
    expect(screen.getByText('No identity')).toBeInTheDocument();
    expect(screen.queryByText('Ready')).not.toBeInTheDocument();
  });
});
