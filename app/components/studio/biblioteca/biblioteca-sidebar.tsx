'use client';

/**
 * PR009.7 — Biblioteca Criativa: the 240px category rail.
 *
 * Presentational only: it renders the nine categories of the spec with the
 * counters it is handed, and reports the chosen one. Hover is gold, the
 * active row is glass — both live in `globals.css` under `.bib-*`.
 *
 * Tablet recolhe (the parent renders it inside a collapsible aside) and
 * mobile moves it into the bottom sheet — the markup is identical in all
 * three so there is exactly one list to keep honest.
 */
import {
  Box,
  CheckCircle2,
  Clapperboard,
  Image as ImageIcon,
  Library,
  Megaphone,
  Music4,
  Star,
  Video,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { CATEGORIES, type CategoryCounts, type CategoryId } from '../../../../lib/assets/biblioteca';

const ICONS: Record<string, LucideIcon> = {
  library: Library,
  image: ImageIcon,
  video: Video,
  audio: Music4,
  star: Star,
  check: CheckCircle2,
  megaphone: Megaphone,
  clapper: Clapperboard,
  box: Box,
};

export type BibliotecaSidebarProps = {
  active: CategoryId;
  counts: CategoryCounts;
  onSelect: (category: CategoryId) => void;
  /** Rendered inside the bottom sheet on mobile — drops the heading. */
  compact?: boolean;
};

export function BibliotecaSidebar({ active, counts, onSelect, compact = false }: BibliotecaSidebarProps) {
  return (
    <nav
      className={`bib-rail ${compact ? 'bib-rail-compact' : ''}`}
      aria-label="Categorias da Biblioteca"
      data-testid="bib-rail"
    >
      {!compact && <p className="bib-rail-title">Categorias</p>}
      <ul>
        {CATEGORIES.map(category => {
          const Icon = ICONS[category.icon];
          const selected = category.id === active;
          return (
            <li key={category.id}>
              <button
                type="button"
                className={`bib-rail-item ${selected ? 'is-active' : ''}`}
                aria-current={selected ? 'true' : undefined}
                onClick={() => onSelect(category.id)}
              >
                <Icon size={17} strokeWidth={selected ? 2.1 : 1.7} aria-hidden="true" />
                <span>{category.label}</span>
                <em data-testid={`bib-count-${category.id}`}>{counts[category.id] ?? 0}</em>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
