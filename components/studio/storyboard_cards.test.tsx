// @vitest-environment jsdom
//
// PR012 — Storyboard Cards: thumbnail, scene, objective, lens, camera,
// duration, mood, and drag/drop reorder wiring (the same contract the
// pre-existing StoryboardCanvas exposed on /studio/director).

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { StoryboardCards, type StoryboardCardScene } from './storyboard-cards';

const scenes: StoryboardCardScene[] = [
  { id: 's1', sceneNumber: 1, title: 'The arrival', objective: 'Establish the world', camera: 'Hero Walk', lens: '35mm anamorphic', duration: 4, mood: 'Epic' },
  { id: 's2', sceneNumber: 2, title: 'Neon crossing', objective: 'Build tension', camera: 'Tracking', lens: '50mm', duration: 5, mood: 'Neo', thumbnailUrl: 'https://example.com/thumb.jpg' },
];

function dataTransfer(initial: Record<string, string> = {}) {
  const store = { ...initial };
  return {
    effectAllowed: '',
    dropEffect: '',
    setData: (key: string, value: string) => { store[key] = value; },
    getData: (key: string) => store[key] ?? '',
  } as unknown as DataTransfer;
}

describe('StoryboardCards', () => {
  it('renders one card per scene with every required field', () => {
    render(<StoryboardCards scenes={scenes} />);
    expect(screen.getByText('Cena 01')).toBeInTheDocument();
    expect(screen.getByText('Cena 02')).toBeInTheDocument();
    expect(screen.getByText('Establish the world')).toBeInTheDocument();
    expect(screen.getByText('Build tension')).toBeInTheDocument();
    expect(screen.getByText('Hero Walk')).toBeInTheDocument();
    expect(screen.getByText('Tracking')).toBeInTheDocument();
    expect(screen.getByText('35mm anamorphic')).toBeInTheDocument();
    expect(screen.getByText('4s')).toBeInTheDocument();
    expect(screen.getByText('5s')).toBeInTheDocument();
    expect(screen.getByText('Epic')).toBeInTheDocument();
    expect(screen.getByText('Neo')).toBeInTheDocument();
  });

  it('renders a cinematic placeholder thumbnail when no thumbnailUrl is given', () => {
    render(<StoryboardCards scenes={scenes} />);
    expect(screen.getByLabelText('Cinematic placeholder for The arrival')).toBeInTheDocument();
    expect(screen.getByAltText('Thumbnail for Neon crossing')).toBeInTheDocument();
  });

  it('calls onSelectScene when a card is clicked', () => {
    const onSelectScene = vi.fn();
    render(<StoryboardCards scenes={scenes} onSelectScene={onSelectScene} />);
    fireEvent.click(screen.getByText('The arrival'));
    expect(onSelectScene).toHaveBeenCalledWith('s1');
  });

  it('supports keyboard selection (Enter and Space)', () => {
    const onSelectScene = vi.fn();
    render(<StoryboardCards scenes={scenes} onSelectScene={onSelectScene} />);
    const cards = screen.getAllByRole('listitem');
    fireEvent.keyDown(cards[0], { key: 'Enter' });
    fireEvent.keyDown(cards[1], { key: ' ' });
    expect(onSelectScene).toHaveBeenNthCalledWith(1, 's1');
    expect(onSelectScene).toHaveBeenNthCalledWith(2, 's2');
  });

  it('ignores irrelevant keys', () => {
    const onSelectScene = vi.fn();
    render(<StoryboardCards scenes={scenes} onSelectScene={onSelectScene} />);
    fireEvent.keyDown(screen.getAllByRole('listitem')[0], { key: 'Tab' });
    expect(onSelectScene).not.toHaveBeenCalled();
  });

  it('marks the selected scene with aria-selected', () => {
    render(<StoryboardCards scenes={scenes} selectedSceneId="s2" />);
    const cards = screen.getAllByRole('listitem');
    expect(cards[0]).toHaveAttribute('aria-selected', 'false');
    expect(cards[1]).toHaveAttribute('aria-selected', 'true');
  });

  it('is draggable by default and calls onReorderScene on drop', () => {
    const onReorderScene = vi.fn();
    render(<StoryboardCards scenes={scenes} onReorderScene={onReorderScene} />);
    const cards = screen.getAllByRole('listitem');
    const dt = dataTransfer();
    fireEvent.dragStart(cards[0], { dataTransfer: dt });
    fireEvent.dragOver(cards[1], { dataTransfer: dt });
    fireEvent.drop(cards[1], { dataTransfer: dt });
    expect(onReorderScene).toHaveBeenCalledWith('s1', 's2');
  });

  it('does not call onReorderScene when dropping a card on itself', () => {
    const onReorderScene = vi.fn();
    render(<StoryboardCards scenes={scenes} onReorderScene={onReorderScene} />);
    const cards = screen.getAllByRole('listitem');
    const dt = dataTransfer();
    fireEvent.dragStart(cards[0], { dataTransfer: dt });
    fireEvent.drop(cards[0], { dataTransfer: dt });
    expect(onReorderScene).not.toHaveBeenCalled();
  });

  it('honors draggable=false', () => {
    render(<StoryboardCards scenes={scenes} draggable={false} />);
    const cards = screen.getAllByRole('listitem');
    expect(cards[0]).toHaveAttribute('draggable', 'false');
  });

  it('renders an empty list gracefully', () => {
    render(<StoryboardCards scenes={[]} />);
    expect(screen.queryAllByRole('listitem')).toHaveLength(0);
  });
});
