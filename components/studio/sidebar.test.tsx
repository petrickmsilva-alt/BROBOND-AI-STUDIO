// @vitest-environment jsdom
//
// PR012 — Sidebar: three groups (CREATE / STUDIO / LIBRARY), fixed width,
// active-state rendering, badge allow-list (GPU/SQL/AI only) and keyboard
// navigability (every nav item is a real <button>).

import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Clapperboard, Film, Gauge, ImageIcon, UserRound } from 'lucide-react';
import { Sidebar, type SidebarGroup } from './sidebar';
import { layout } from '../../lib/theme/tokens';

const groups: SidebarGroup[] = [
  {
    id: 'create',
    label: 'CREATE',
    items: [
      { id: 'director', label: 'Director', icon: Film },
      { id: 'storyboard', label: 'Storyboard', icon: Clapperboard },
      { id: 'render', label: 'Render Queue', icon: Gauge, badge: 'GPU' },
    ],
  },
  {
    id: 'studio',
    label: 'STUDIO',
    items: [
      { id: 'personas', label: 'Personas', icon: UserRound, badge: 'AI' },
      { id: 'image', label: 'Image', icon: ImageIcon },
      { id: 'video', label: 'Video', icon: Clapperboard },
      { id: 'campaigns', label: 'Campaigns', icon: Film },
    ],
  },
  {
    id: 'library',
    label: 'LIBRARY',
    items: [
      { id: 'assets', label: 'Biblioteca', icon: ImageIcon },
      { id: 'knowledge', label: 'Knowledge', icon: Film, badge: 'SQL' },
      { id: 'continuity', label: 'Continuity', icon: Film },
      { id: 'quality', label: 'Quality', icon: Gauge },
    ],
  },
];

afterEach(() => {
  vi.restoreAllMocks();
});

describe('Sidebar', () => {
  it('renders the three required groups in order: CREATE, STUDIO, LIBRARY', () => {
    render(<Sidebar groups={groups} activeId="director" onNavigate={() => {}} />);
    const labels = screen.getAllByText(/CREATE|STUDIO|LIBRARY/).map(el => el.textContent);
    expect(labels).toEqual(['CREATE', 'STUDIO', 'LIBRARY']);
  });

  it('renders every item across every group as an accessible navigation button', () => {
    render(<Sidebar groups={groups} activeId="director" onNavigate={() => {}} />);
    ['Director', 'Storyboard', 'Render Queue', 'Personas', 'Image', 'Video', 'Campaigns', 'Biblioteca', 'Knowledge', 'Continuity', 'Quality'].forEach(label => {
      expect(screen.getByRole('button', { name: new RegExp(label) })).toBeInTheDocument();
    });
  });

  it('marks the active item with aria-current="page"', () => {
    render(<Sidebar groups={groups} activeId="storyboard" onNavigate={() => {}} />);
    const active = screen.getByRole('button', { name: /Storyboard/ });
    expect(active).toHaveAttribute('aria-current', 'page');
    const inactive = screen.getByRole('button', { name: /Director/ });
    expect(inactive).not.toHaveAttribute('aria-current');
  });

  it('calls onNavigate with the item id when clicked', () => {
    const onNavigate = vi.fn();
    render(<Sidebar groups={groups} activeId="director" onNavigate={onNavigate} />);
    fireEvent.click(screen.getByRole('button', { name: /Storyboard/ }));
    expect(onNavigate).toHaveBeenCalledWith('storyboard');
  });

  it('renders badges only for GPU, SQL and AI, dropping anything else', () => {
    const groupsWithBadBadge: SidebarGroup[] = [
      {
        id: 'create',
        label: 'CREATE',
        items: [
          { id: 'director', label: 'Director', icon: Film, badge: 'NEW' },
          { id: 'render', label: 'Render Queue', icon: Gauge, badge: 'GPU' },
        ],
      },
    ];
    render(<Sidebar groups={groupsWithBadBadge} activeId="director" onNavigate={() => {}} />);
    expect(screen.queryByText('NEW')).not.toBeInTheDocument();
    expect(screen.getByText('GPU')).toBeInTheDocument();
  });

  it('renders the SQL and AI badges when present', () => {
    render(<Sidebar groups={groups} activeId="director" onNavigate={() => {}} />);
    expect(screen.getByText('SQL')).toBeInTheDocument();
    expect(screen.getByText('AI')).toBeInTheDocument();
  });

  it('is fixed at the design-system sidebar width', () => {
    render(<Sidebar groups={groups} activeId="director" onNavigate={() => {}} />);
    const sidebar = screen.getByTestId('bb-sidebar');
    expect(sidebar.style.width).toBe(`${layout.sidebarWidth}px`);
  });

  it('collapses to zero width when collapsed=true', () => {
    render(<Sidebar groups={groups} activeId="director" onNavigate={() => {}} collapsed />);
    const sidebar = screen.getByTestId('bb-sidebar');
    expect(sidebar.style.width).toBe('0px');
    expect(sidebar.className).toContain('bb-sidebar-collapsed');
  });

  it('renders the brand row and calls onBrandClick when provided', () => {
    const onBrandClick = vi.fn();
    render(<Sidebar groups={groups} activeId="director" onNavigate={() => {}} brand={{ name: 'BROBOND', sub: 'AI STUDIO' }} onBrandClick={onBrandClick} />);
    fireEvent.click(screen.getByRole('button', { name: /BROBOND/ }));
    expect(onBrandClick).toHaveBeenCalledTimes(1);
    expect(screen.getByText('AI STUDIO')).toBeInTheDocument();
  });

  it('omits the brand row when no brand is supplied', () => {
    render(<Sidebar groups={groups} activeId="director" onNavigate={() => {}} />);
    expect(screen.queryByText('AI STUDIO')).not.toBeInTheDocument();
  });

  it('renders custom footer content when provided', () => {
    render(<Sidebar groups={groups} activeId="director" onNavigate={() => {}} footer={<div>Signed in</div>} />);
    expect(screen.getByText('Signed in')).toBeInTheDocument();
  });

  it('omits the footer container when none is supplied', () => {
    const { container } = render(<Sidebar groups={groups} activeId="director" onNavigate={() => {}} />);
    expect(container.querySelector('.bb-sidebar-footer')).toBeNull();
  });
});
