/**
 * PR009.7 — Biblioteca Criativa: the pure domain of the professional
 * library UI.
 *
 * Interface only. Nothing here talks to the network, the DOM or React —
 * it decides *what the Biblioteca shows* over exactly the data the
 * existing `/api/v1/assets` surface already returns (`LibraryAsset`).
 * No backend, route, JWT or upload contract is touched by this module.
 *
 * Honesty contract (unchanged, repo-wide): an unknown value renders as
 * the em dash `—`, never as a zero, a guessed unit or an invented label.
 * Categories, tags and quality badges are *derived* from stored metadata;
 * when the metadata is absent the asset simply does not match — it is
 * never fabricated into a category.
 */
import type { LibraryAsset } from './library';

export type { LibraryAsset } from './library';

// ---------------------------------------------------------------------------
// Nomenclature — the interface says "Biblioteca", the API keeps "assets"
// ---------------------------------------------------------------------------

/** Every user-facing string of the module, in one place (REGRA 1). */
export const BIBLIOTECA_COPY = {
  /** Sidebar entry of the studio shell. */
  navLabel: 'Biblioteca',
  /** Header title. */
  title: 'Biblioteca Criativa',
  /** Header subtitle. */
  subtitle: 'Gerencie imagens, vídeos e arquivos da Brobond.',
  /** Breadcrumb tail (the head stays "Workspace"). */
  breadcrumb: 'Workspace / Biblioteca',
  /** The call to action that used to read "Open Library". */
  openLibrary: 'Abrir Biblioteca',
  /** The gold header button. */
  upload: 'Upload',
  /** The dashed drop area. */
  dropHint: 'Arraste imagens e vídeos aqui',
  searchPlaceholder: 'Pesquisar por nome, tipo ou tag',
} as const;

// ---------------------------------------------------------------------------
// Kinds — the badge printed over every thumbnail
// ---------------------------------------------------------------------------

export type LibraryKind = 'image' | 'video' | 'audio' | 'other';

/** The stored `kind` normalized to the four the Biblioteca renders. */
export function assetKind(asset: Pick<LibraryAsset, 'kind' | 'content_type'>): LibraryKind {
  const raw = (asset.kind ?? '').toLowerCase();
  if (raw === 'image' || raw === 'video' || raw === 'audio') return raw;
  const mime = (asset.content_type ?? '').toLowerCase();
  if (mime.startsWith('image/')) return 'image';
  if (mime.startsWith('video/')) return 'video';
  if (mime.startsWith('audio/')) return 'audio';
  return 'other';
}

/** IMG · VIDEO · AUDIO — the badge text (never a guessed format). */
export const KIND_BADGE: Record<LibraryKind, string> = {
  image: 'IMG',
  video: 'VIDEO',
  audio: 'AUDIO',
  other: 'FILE',
};

// ---------------------------------------------------------------------------
// Categories — the 240px sidebar, each with its own counter
// ---------------------------------------------------------------------------

export type CategoryId =
  | 'todos'
  | 'imagens'
  | 'videos'
  | 'audios'
  | 'favoritos'
  | 'aprovados'
  | 'campanhas'
  | 'bastidores'
  | 'produtos';

export type CategoryDefinition = {
  id: CategoryId;
  label: string;
  /** Lucide icon name the sidebar maps to a component. */
  icon: string;
};

export const CATEGORIES: readonly CategoryDefinition[] = [
  { id: 'todos', label: 'Todos', icon: 'library' },
  { id: 'imagens', label: 'Imagens', icon: 'image' },
  { id: 'videos', label: 'Vídeos', icon: 'video' },
  { id: 'audios', label: 'Áudios', icon: 'audio' },
  { id: 'favoritos', label: 'Favoritos', icon: 'star' },
  { id: 'aprovados', label: 'Aprovados', icon: 'check' },
  { id: 'campanhas', label: 'Campanhas', icon: 'megaphone' },
  { id: 'bastidores', label: 'Bastidores', icon: 'clapper' },
  { id: 'produtos', label: 'Produtos', icon: 'box' },
];

/** The themed categories — the ones classified by the words in the metadata. */
type ThemedCategoryId = 'campanhas' | 'bastidores' | 'produtos';

/** The words (already lowercase, accent-free) each themed category looks for. */
const CATEGORY_KEYWORDS: Record<ThemedCategoryId, readonly string[]> = {
  campanhas: ['campanha', 'campaign', 'lookback', 'lookbook'],
  bastidores: ['bastidor', 'bastidores', 'backstage', 'making of', 'makingof', 'bts'],
  produtos: ['produto', 'produtos', 'product', 'packshot', 'still'],
};

/** Lowercase + accent-free, so "Verão" matches "verao" in a search box. */
export function normalizeText(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}

/** Everything searchable/classifiable about an asset, as one haystack. */
function metadataWords(asset: LibraryAsset): string {
  return normalizeText(
    [asset.name, asset.project, asset.persona, asset.source, ...(asset.tags ?? [])]
      .filter((value): value is string => typeof value === 'string' && value.length > 0)
      .join(' '),
  );
}

export function matchesCategory(
  asset: LibraryAsset,
  category: CategoryId,
  favorites: ReadonlySet<string>,
): boolean {
  switch (category) {
    case 'todos':
      return true;
    case 'imagens':
      return assetKind(asset) === 'image';
    case 'videos':
      return assetKind(asset) === 'video';
    case 'audios':
      return assetKind(asset) === 'audio';
    case 'favoritos':
      return favorites.has(asset.id);
    case 'aprovados':
      return qualityBadge(asset).id === 'aprovado';
    default: {
      const keywords = CATEGORY_KEYWORDS[category];
      const haystack = metadataWords(asset);
      return keywords.some(word => haystack.includes(word));
    }
  }
}

export type CategoryCounts = Record<CategoryId, number>;

export function countCategories(
  items: readonly LibraryAsset[],
  favorites: ReadonlySet<string>,
): CategoryCounts {
  const counts = {} as CategoryCounts;
  CATEGORIES.forEach(category => {
    counts[category.id] = items.filter(item => matchesCategory(item, category.id, favorites)).length;
  });
  return counts;
}

// ---------------------------------------------------------------------------
// Quality — the lateral badge (uses `quality_status` when the API sends it)
// ---------------------------------------------------------------------------

export type QualityBadgeId = 'aprovado' | 'revisao' | 'rascunho';

export type QualityBadge = { id: QualityBadgeId; label: string };

const QUALITY_LABELS: Record<QualityBadgeId, string> = {
  aprovado: 'Aprovado',
  revisao: 'Em revisão',
  rascunho: 'Rascunho',
};

/**
 * `quality_status` first — it is the Quality Engine's own word. When the
 * row predates it, the stored score falls back onto the engine's bands
 * (>= 85 approved · >= 70 review · below that a draft). With neither, the
 * asset is honestly a draft, never an invented approval.
 */
export function qualityBadge(asset: Pick<LibraryAsset, 'quality_status' | 'quality_score'>): QualityBadge {
  const status = normalizeText(asset.quality_status ?? '');
  if (status) {
    if (status.includes('approv') || status.includes('aprov') || status.includes('masterpiece')) {
      return { id: 'aprovado', label: QUALITY_LABELS.aprovado };
    }
    if (status.includes('review') || status.includes('revis') || status.includes('pending')) {
      return { id: 'revisao', label: QUALITY_LABELS.revisao };
    }
    return { id: 'rascunho', label: QUALITY_LABELS.rascunho };
  }
  const score = asset.quality_score;
  if (score == null) return { id: 'rascunho', label: QUALITY_LABELS.rascunho };
  if (score >= 85) return { id: 'aprovado', label: QUALITY_LABELS.aprovado };
  if (score >= 70) return { id: 'revisao', label: QUALITY_LABELS.revisao };
  return { id: 'rascunho', label: QUALITY_LABELS.rascunho };
}

// ---------------------------------------------------------------------------
// Tags — visual only, built from metadata that already exists
// ---------------------------------------------------------------------------

/**
 * The chips a card shows: the stored tags first, then the project and the
 * persona (they read as tags in the product's own vocabulary). Uppercase,
 * de-duplicated, never invented — an asset without metadata shows none.
 */
export function displayTags(asset: LibraryAsset, limit = 3): string[] {
  const candidates = [...(asset.tags ?? []), asset.project ?? '', asset.persona ?? ''];
  const seen = new Set<string>();
  const tags: string[] = [];
  candidates.forEach(candidate => {
    const value = (candidate ?? '').trim();
    if (!value) return;
    const key = normalizeText(value);
    if (seen.has(key)) return;
    seen.add(key);
    tags.push(value.toUpperCase());
  });
  return tags.slice(0, limit);
}

// ---------------------------------------------------------------------------
// Busca — instant, over name, type and tag
// ---------------------------------------------------------------------------

export function matchesSearch(asset: LibraryAsset, query: string): boolean {
  const needle = normalizeText(query);
  if (!needle) return true;
  const kind = assetKind(asset);
  const haystack = [
    metadataWords(asset),
    kind,
    normalizeText(KIND_BADGE[kind]),
    normalizeText(asset.content_type ?? ''),
  ].join(' ');
  return haystack.includes(needle);
}

// ---------------------------------------------------------------------------
// Ordenação
// ---------------------------------------------------------------------------

export type SortId = 'recentes' | 'antigos' | 'nome-az' | 'nome-za' | 'maiores';

export const SORT_OPTIONS: ReadonlyArray<{ id: SortId; label: string }> = [
  { id: 'recentes', label: 'Mais recente' },
  { id: 'antigos', label: 'Mais antigo' },
  { id: 'nome-az', label: 'Nome A-Z' },
  { id: 'nome-za', label: 'Nome Z-A' },
  { id: 'maiores', label: 'Maior arquivo' },
];

function createdAtMs(asset: LibraryAsset): number {
  const time = new Date(asset.created_at).getTime();
  return Number.isNaN(time) ? 0 : time;
}

/** A pure, stable sort — the input array is never mutated. */
export function sortLibrary(items: readonly LibraryAsset[], sort: SortId): LibraryAsset[] {
  const copy = [...items];
  switch (sort) {
    case 'antigos':
      return copy.sort((a, b) => createdAtMs(a) - createdAtMs(b));
    case 'nome-az':
      return copy.sort((a, b) => a.name.localeCompare(b.name, 'pt-BR'));
    case 'nome-za':
      return copy.sort((a, b) => b.name.localeCompare(a.name, 'pt-BR'));
    case 'maiores':
      return copy.sort((a, b) => (b.size_bytes ?? 0) - (a.size_bytes ?? 0));
    default:
      return copy.sort((a, b) => createdAtMs(b) - createdAtMs(a));
  }
}

// ---------------------------------------------------------------------------
// The whole view state, applied in one pass
// ---------------------------------------------------------------------------

export type BibliotecaView = {
  category: CategoryId;
  search: string;
  sort: SortId;
};

export const DEFAULT_VIEW: BibliotecaView = {
  category: 'todos',
  search: '',
  sort: 'recentes',
};

export function applyView(
  items: readonly LibraryAsset[],
  view: BibliotecaView,
  favorites: ReadonlySet<string>,
): LibraryAsset[] {
  const filtered = items.filter(
    item => matchesCategory(item, view.category, favorites) && matchesSearch(item, view.search),
  );
  return sortLibrary(filtered, view.sort);
}

// ---------------------------------------------------------------------------
// Formatters — pt-BR, honest about what it does not know
// ---------------------------------------------------------------------------

export const UNKNOWN = '—';

/** dd/mm/aaaa, the format the studio's Brazilian team reads. */
export function formatDateBR(iso: string | null | undefined): string {
  if (!iso) return UNKNOWN;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return UNKNOWN;
  const day = String(date.getUTCDate()).padStart(2, '0');
  const month = String(date.getUTCMonth() + 1).padStart(2, '0');
  return `${day}/${month}/${date.getUTCFullYear()}`;
}

export function formatSizeBR(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes) || bytes < 0) return UNKNOWN;
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'] as const;
  let value = bytes;
  let unit = 'B';
  for (const next of units) {
    if (value < 1024) break;
    value /= 1024;
    unit = next;
  }
  const rounded = value >= 100 ? String(Math.round(value)) : value.toFixed(1);
  return `${rounded.replace('.', ',')} ${unit}`;
}

/** The resolution a card prints — stored string first, then width×height. */
export function resolutionBR(asset: Pick<LibraryAsset, 'resolution' | 'width' | 'height'>): string {
  if (asset.resolution) return asset.resolution;
  if (asset.width && asset.height) return `${asset.width}×${asset.height}`;
  return UNKNOWN;
}

export function formatClock(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return UNKNOWN;
  const whole = Math.floor(seconds);
  const minutes = Math.floor(whole / 60);
  const rest = whole % 60;
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
}
