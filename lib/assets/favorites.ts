/**
 * PR009.7 — Biblioteca Criativa: the local favorites seam.
 *
 * "Ícone estrela. Clique salva localmente. Não alterar backend." — so the
 * star is a purely client-side mark: no endpoint, no column, no JWT.
 *
 * Why a cookie and not the Memory Adapter: the adapter's storage keys are
 * frozen by contract (backend `test_project_memory_contract.py` allows
 * exactly PROJECT_MEMORY_KEY / AUTH_TOKEN_KEY / LEGACY_PERSONA_ID_KEY), and
 * a favorite is none of those. This mirrors the precedent set by
 * `lib/memory/remembered_login.ts` — a named cookie seam, documented, with
 * its own expiry, and the only file in the module that touches `document.cookie`.
 *
 * What is stored: asset ids, nothing else. Never a URL, never a credential.
 */

const FAVORITES_COOKIE = 'brobond_biblioteca_favoritos';

/** A year: the mark is a preference, not a session. */
export const FAVORITES_DAYS = 365;

const DAY_SECONDS = 24 * 60 * 60;

/** Cookies cap around 4KB; ids are short, but the list stays bounded. */
const MAX_FAVORITES = 400;

function readJar(): string | null {
  if (typeof document === 'undefined') return null;
  try {
    return document.cookie;
  } catch {
    return null;
  }
}

function writeJar(value: string): void {
  if (typeof document === 'undefined') return;
  try {
    document.cookie = `${FAVORITES_COOKIE}=${value}; Max-Age=${FAVORITES_DAYS * DAY_SECONDS}; Path=/; SameSite=Lax`;
  } catch {
    // Best effort: a blocked cookie must never break the Biblioteca.
  }
}

function encodeId(id: string): string {
  try {
    return encodeURIComponent(id);
  } catch {
    return '';
  }
}

function decodeId(raw: string): string {
  try {
    return decodeURIComponent(raw);
  } catch {
    return '';
  }
}

/** The ids marked on this device. Never throws; an unreadable jar is empty. */
export function loadFavorites(): Set<string> {
  const jar = readJar();
  if (!jar) return new Set();
  const entry = jar.split('; ').find(part => part.startsWith(`${FAVORITES_COOKIE}=`));
  if (!entry) return new Set();
  const raw = entry.slice(FAVORITES_COOKIE.length + 1);
  if (!raw) return new Set();
  const ids = raw
    .split(',')
    .map(decodeId)
    .filter(id => id.length > 0);
  return new Set(ids);
}

export function saveFavorites(ids: ReadonlySet<string>): void {
  const serialized = Array.from(ids).slice(0, MAX_FAVORITES).map(encodeId).filter(Boolean).join(',');
  writeJar(serialized);
}

/** Pure toggle: returns the next set, leaving the input untouched. */
export function toggleFavorite(ids: ReadonlySet<string>, assetId: string): Set<string> {
  const next = new Set(ids);
  if (next.has(assetId)) next.delete(assetId);
  else next.add(assetId);
  return next;
}
