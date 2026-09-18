'use client';

/**
 * PR013 (V4.0.1 · ETAPA 5) — the library filter bar.
 *
 * One controlled component: every control writes back into the same
 * `LibraryFilters` object. Search is instant — it re-filters in memory on
 * every keystroke (the parent owns the apply step; the API's own filter
 * parameters stay available for consumers that want server-side cuts).
 */
import { Search, X } from 'lucide-react';
import {
  EMPTY_LIBRARY_FILTERS,
  SCORE_FLOOR_OPTIONS,
  filtersAreActive,
  type LibraryFacets,
  type LibraryFilters,
} from '../../../../lib/assets/library';

export type AssetFilterBarProps = {
  filters: LibraryFilters;
  onChange: (next: LibraryFilters) => void;
  facets: LibraryFacets;
  resultCount: number;
  totalCount: number;
};

const KIND_OPTIONS: ReadonlyArray<{ value: LibraryFilters['kind']; label: string }> = [
  { value: '', label: 'All types' },
  { value: 'image', label: 'Images' },
  { value: 'video', label: 'Videos' },
];

export function AssetFilterBar({ filters, onChange, facets, resultCount, totalCount }: AssetFilterBarProps) {
  const set = (patch: Partial<LibraryFilters>) => onChange({ ...filters, ...patch });
  const active = filtersAreActive(filters);

  return (
    <div className="al-filters" data-testid="al-filters">
      <div className="al-filters-row">
        <label className="al-search">
          <Search size={14} aria-hidden="true" />
          <input
            value={filters.search}
            onChange={event => set({ search: event.target.value })}
            placeholder="Search by name or tag"
            aria-label="Search by name or tag"
          />
          {filters.search && (
            <button type="button" aria-label="Clear search" onClick={() => set({ search: '' })}>
              <X size={12} />
            </button>
          )}
        </label>

        <div className="al-kind-tabs" role="group" aria-label="Filter by type">
          {KIND_OPTIONS.map(option => (
            <button
              key={option.label}
              type="button"
              className={filters.kind === option.value ? 'selected' : ''}
              aria-pressed={filters.kind === option.value}
              onClick={() => set({ kind: option.value })}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="al-filters-row">
        <FacetSelect label="Project" value={filters.project} options={facets.projects} onSelect={value => set({ project: value })} />
        <FacetSelect label="Persona" value={filters.persona} options={facets.personas} onSelect={value => set({ persona: value })} />
        <FacetSelect label="Provider" value={filters.provider} options={facets.providers} onSelect={value => set({ provider: value })} />

        <div className="al-score-tabs" role="group" aria-label="Minimum quality score">
          {SCORE_FLOOR_OPTIONS.map(option => (
            <button
              key={option.value}
              type="button"
              className={filters.minScore === option.value ? 'selected' : ''}
              aria-pressed={filters.minScore === option.value}
              onClick={() => set({ minScore: option.value })}
            >
              {option.label}
            </button>
          ))}
        </div>

        <label className="al-date">
          <span>From</span>
          <input type="date" value={filters.dateFrom} aria-label="From date" onChange={event => set({ dateFrom: event.target.value })} />
        </label>
        <label className="al-date">
          <span>To</span>
          <input type="date" value={filters.dateTo} aria-label="To date" onChange={event => set({ dateTo: event.target.value })} />
        </label>

        {active && (
          <button type="button" className="al-clear" onClick={() => onChange({ ...EMPTY_LIBRARY_FILTERS })}>
            <X size={12} /> Clear
          </button>
        )}
        <span className="al-count" aria-live="polite">
          {resultCount === totalCount ? `${totalCount} assets` : `${resultCount} of ${totalCount}`}
        </span>
      </div>
    </div>
  );
}

function FacetSelect({
  label,
  value,
  options,
  onSelect,
}: {
  label: string;
  value: string;
  options: readonly string[];
  onSelect: (value: string) => void;
}) {
  return (
    <label className="al-facet">
      <span>{label}</span>
      <select value={value} aria-label={`Filter by ${label.toLowerCase()}`} onChange={event => onSelect(event.target.value)}>
        <option value="">All</option>
        {options.map(option => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}
