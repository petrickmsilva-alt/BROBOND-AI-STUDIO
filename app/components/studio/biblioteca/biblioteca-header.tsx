'use client';

/**
 * PR009.7 — Biblioteca Criativa: the 72px header.
 *
 * Left: 📚 Biblioteca Criativa + the subtitle. Right: pesquisa, filtro,
 * ordenação and the gold Upload button. The upload button is the same
 * hidden-input affordance the module already used — it feeds the existing
 * POST /api/v1/assets/upload flow untouched.
 */
import { useEffect, useRef, useState } from 'react';
import { ChevronDown, Search, SlidersHorizontal, UploadCloud, X } from 'lucide-react';
import {
  BIBLIOTECA_COPY,
  CATEGORIES,
  SORT_OPTIONS,
  type CategoryId,
  type SortId,
} from '../../../../lib/assets/biblioteca';
import { UPLOAD_ACCEPT_ATTR } from '../../../../lib/assets/library';

export type BibliotecaHeaderProps = {
  search: string;
  onSearch: (value: string) => void;
  category: CategoryId;
  onCategory: (category: CategoryId) => void;
  sort: SortId;
  onSort: (sort: SortId) => void;
  onFiles: (files: File[]) => void;
  /** Opens the mobile bottom sheet; hidden on desktop by CSS. */
  onOpenFilters: () => void;
};

/** Both tables are exhaustive over their id unions — no fallback to invent. */
function categoryLabel(category: CategoryId): string {
  return (CATEGORIES.find(item => item.id === category) as { label: string }).label;
}

function sortLabel(sort: SortId): string {
  return (SORT_OPTIONS.find(item => item.id === sort) as { label: string }).label;
}

export function BibliotecaHeader({
  search,
  onSearch,
  category,
  onCategory,
  sort,
  onSort,
  onFiles,
  onOpenFilters,
}: BibliotecaHeaderProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <header className="bib-header" data-testid="bib-header">
      <div className="bib-header-copy">
        <h1>
          <span aria-hidden="true">📚</span> {BIBLIOTECA_COPY.title}
        </h1>
        <p>{BIBLIOTECA_COPY.subtitle}</p>
      </div>

      <div className="bib-header-tools">
        <label className="bib-search">
          <Search size={15} aria-hidden="true" />
          <input
            value={search}
            onChange={event => onSearch(event.target.value)}
            placeholder={BIBLIOTECA_COPY.searchPlaceholder}
            aria-label="Pesquisar na Biblioteca"
            type="search"
          />
          {search && (
            <button type="button" aria-label="Limpar pesquisa" onClick={() => onSearch('')}>
              <X size={12} />
            </button>
          )}
        </label>

        <Dropdown
          label="Filtro"
          value={categoryLabel(category)}
          ariaLabel="Filtrar categoria"
          options={CATEGORIES.map(item => ({ id: item.id, label: item.label }))}
          selected={category}
          onSelect={id => onCategory(id as CategoryId)}
        />

        <Dropdown
          label="Ordenar"
          value={sortLabel(sort)}
          ariaLabel="Ordenar Biblioteca"
          options={SORT_OPTIONS.map(item => ({ id: item.id, label: item.label }))}
          selected={sort}
          onSelect={id => onSort(id as SortId)}
        />

        <button type="button" className="bib-sheet-trigger" onClick={onOpenFilters} aria-label="Abrir filtros">
          <SlidersHorizontal size={16} />
        </button>

        <button type="button" className="bib-upload" onClick={() => inputRef.current?.click()}>
          <UploadCloud size={15} aria-hidden="true" /> {BIBLIOTECA_COPY.upload}
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={UPLOAD_ACCEPT_ATTR}
          className="bib-file-input"
          aria-label="Selecionar arquivos para enviar"
          onChange={event => {
            if (event.target.files?.length) onFiles(Array.from(event.target.files));
            event.target.value = '';
          }}
        />
      </div>
    </header>
  );
}

type DropdownOption = { id: string; label: string };

/** A small menu — native selects cannot carry the premium surface. */
function Dropdown({
  label,
  value,
  ariaLabel,
  options,
  selected,
  onSelect,
}: {
  label: string;
  value: string;
  ariaLabel: string;
  options: readonly DropdownOption[];
  selected: string;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const onAway = (event: MouseEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onAway);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onAway);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className="bib-dropdown" ref={root}>
      <button
        type="button"
        className={open ? 'bib-dropdown-trigger is-open' : 'bib-dropdown-trigger'}
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-haspopup="listbox"
        onClick={() => setOpen(value => !value)}
      >
        <span className="bib-dropdown-label">{label}</span>
        <strong>{value}</strong>
        <ChevronDown size={13} aria-hidden="true" />
      </button>
      {open && (
        <ul className="bib-dropdown-menu" role="listbox" aria-label={ariaLabel}>
          {options.map(option => (
            <li key={option.id}>
              <button
                type="button"
                role="option"
                aria-selected={option.id === selected}
                className={option.id === selected ? 'is-selected' : ''}
                onClick={() => {
                  onSelect(option.id);
                  setOpen(false);
                }}
              >
                {option.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
