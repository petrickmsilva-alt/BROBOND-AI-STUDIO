// PR009.6 — "Lembrar de mim": the remembered-login seam.
//
// Why a cookie and not the Memory Adapter: the adapter's storage keys are
// frozen by contract (backend `test_project_memory_contract.py` allows
// exactly PROJECT_MEMORY_KEY / AUTH_TOKEN_KEY / LEGACY_PERSONA_ID_KEY), and
// a remembered login is none of those — it is not project memory and it is
// emphatically not a credential. A cookie is the canonical mechanism for
// "stay signed in on this device": it carries a native 30-day expiry, so
// the browser itself retires the record — no cleanup sweep, no drift.
//
// What is stored: email + display name, nothing else. The JWT in the
// Memory Adapter's auth seam remains the only credential; this record only
// lets the login screen greet a returning creator and lets Home restore
// the session through the existing GET /api/v1/auth/me.

/** Cookie name. Mirrors the adapter's naming convention (`brobond_*`). */
const REMEMBERED_LOGIN_COOKIE = 'brobond_remembered_login';

/** The product decision: "Lembrar de mim" keeps the session for 30 days. */
export const REMEMBERED_LOGIN_DAYS = 30;

export interface RememberedLogin {
  email: string;
  name: string;
  /** Unix ms when the record lapses. Defensive only: the cookie's own
   *  Max-Age already expires it — this guards clock-skewed or hand-edited
   *  cookies. */
  expiresAt: number;
}

const DAY_MS = 24 * 60 * 60 * 1000;

function readCookieJar(): string | null {
  if (typeof document === 'undefined') return null;
  try {
    return document.cookie;
  } catch {
    return null;
  }
}

/** URL-safe encoding for the two free-text fields (email / name). */
function encodeField(value: string): string {
  try {
    return encodeURIComponent(value);
  } catch {
    return '';
  }
}

function decodeField(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return '';
  }
}

function serialize(record: RememberedLogin): string {
  // `|` never survives encodeField, so it is a safe field separator.
  return `${encodeField(record.email)}|${encodeField(record.name)}|${record.expiresAt}`;
}

function deserialize(raw: string): RememberedLogin | null {
  const [emailPart, namePart, expiresPart] = raw.split('|');
  const email = decodeField(emailPart ?? '');
  if (!email) return null;
  const expiresAt = Number(expiresPart);
  if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) return null;
  return { email, name: decodeField(namePart ?? '') || email, expiresAt };
}

export function setRememberedLogin(email: string, name: string, days = REMEMBERED_LOGIN_DAYS): void {
  if (typeof document === 'undefined') return;
  if (!email) return;
  const expiresAt = Date.now() + days * DAY_MS;
  try {
    document.cookie = `${REMEMBERED_LOGIN_COOKIE}=${serialize({ email, name, expiresAt })}; Max-Age=${days * 24 * 60 * 60}; Path=/; SameSite=Lax`;
  } catch {
    // Best effort: a blocked cookie must never break a successful login.
  }
}

export function getRememberedLogin(): RememberedLogin | null {
  const jar = readCookieJar();
  if (!jar) return null;
  const match = jar.split('; ').find(part => part.startsWith(`${REMEMBERED_LOGIN_COOKIE}=`));
  if (!match) return null;
  return deserialize(match.slice(REMEMBERED_LOGIN_COOKIE.length + 1));
}

export function clearRememberedLogin(): void {
  if (typeof document === 'undefined') return;
  try {
    document.cookie = `${REMEMBERED_LOGIN_COOKIE}=; Max-Age=0; Path=/; SameSite=Lax`;
  } catch {
    // Best effort.
  }
}
