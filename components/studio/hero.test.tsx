// @vitest-environment jsdom
//
// PR012 — Hero Workspace: Creative Brief (left) + Live Storyboard Preview
// (right), including the cinematic-placeholder path used before any scene
// has rendered.

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { HeroWorkspace, type HeroWorkspaceScenePreview } from './hero-workspace';

function renderHero(overrides: Partial<Parameters<typeof HeroWorkspace>[0]> = {}) {
  const props = {
    brief: '',
    onBriefChange: vi.fn(),
    sceneCount: 4,
    onSceneCountChange: vi.fn(),
    language: 'pt-BR',
    onLanguageChange: vi.fn(),
    platform: 'instagram',
    onPlatformChange: vi.fn(),
    onSubmit: vi.fn(),
    scenes: [] as HeroWorkspaceScenePreview[],
    ...overrides,
  };
  render(<HeroWorkspace {...props} />);
  return props;
}

describe('HeroWorkspace', () => {
  it('renders the Creative Brief panel with textarea, scene count, language and platform', () => {
    renderHero();
    expect(screen.getByText('Creative Brief')).toBeInTheDocument();
    expect(screen.getByLabelText('Creative brief')).toBeInTheDocument();
    expect(screen.getByLabelText(/Cenas/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Idioma/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Plataforma/)).toBeInTheDocument();
  });

  it('renders one primary action button', () => {
    renderHero({ brief: 'A hero walks through neon rain' });
    expect(screen.getByRole('button', { name: /Criar Produção/ })).toBeInTheDocument();
  });

  it('disables the primary action when the brief is empty', () => {
    renderHero({ brief: '   ' });
    expect(screen.getByRole('button', { name: /Criar Produção/ })).toBeDisabled();
  });

  it('enables the primary action once the brief has content and calls onSubmit', () => {
    const onSubmit = vi.fn();
    renderHero({ brief: 'A hero walks through neon rain', onSubmit });
    const button = screen.getByRole('button', { name: /Criar Produção/ });
    expect(button).not.toBeDisabled();
    fireEvent.click(button);
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('shows a submitting state and keeps the action disabled while submitting', () => {
    renderHero({ brief: 'Ready', submitting: true });
    expect(screen.getByRole('button', { name: /Dirigindo/ })).toBeDisabled();
  });

  it('propagates textarea changes through onBriefChange', () => {
    const onBriefChange = vi.fn();
    renderHero({ onBriefChange });
    fireEvent.change(screen.getByLabelText('Creative brief'), { target: { value: 'New brief text' } });
    expect(onBriefChange).toHaveBeenCalledWith('New brief text');
  });

  it('propagates scene count, language and platform changes', () => {
    const onSceneCountChange = vi.fn();
    const onLanguageChange = vi.fn();
    const onPlatformChange = vi.fn();
    renderHero({ onSceneCountChange, onLanguageChange, onPlatformChange });
    fireEvent.change(screen.getByLabelText(/Cenas/), { target: { value: '6' } });
    expect(onSceneCountChange).toHaveBeenCalledWith(6);
    fireEvent.change(screen.getByLabelText(/Idioma/), { target: { value: 'en' } });
    expect(onLanguageChange).toHaveBeenCalledWith('en');
    fireEvent.change(screen.getByLabelText(/Plataforma/), { target: { value: 'tiktok' } });
    expect(onPlatformChange).toHaveBeenCalledWith('tiktok');
  });

  it('shows the empty-preview cinematic placeholder when there are no scenes yet', () => {
    renderHero({ scenes: [] });
    expect(screen.getByText('Nenhuma cena ainda')).toBeInTheDocument();
  });

  it('renders scene thumbnails even without a render, using placeholders when no thumbnail url exists', () => {
    renderHero({
      scenes: [
        { id: 's1', sceneNumber: 1, title: 'The arrival', mood: 'Epic' },
        { id: 's2', sceneNumber: 2, title: 'Neon crossing', mood: 'Neo', thumbnailUrl: 'https://example.com/thumb.jpg' },
      ],
    });
    expect(screen.getByText('The arrival')).toBeInTheDocument();
    expect(screen.getByText('Neon crossing')).toBeInTheDocument();
    expect(screen.getByText('SCENE 01')).toBeInTheDocument();
    expect(screen.getByAltText('Preview of Neon crossing')).toBeInTheDocument();
  });

  it('reflects the live scene count in the preview heading', () => {
    renderHero({ scenes: [{ id: 's1', sceneNumber: 1, title: 'Scene one' }] });
    expect(screen.getByText('1 cenas prontas para direção')).toBeInTheDocument();
  });

  it('accepts custom language and platform option lists', () => {
    renderHero({
      languageOptions: [{ value: 'fr', label: 'Français' }],
      platformOptions: [{ value: 'ads', label: 'Ads' }],
    });
    expect(screen.getByRole('option', { name: 'Français' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Ads' })).toBeInTheDocument();
  });
});
