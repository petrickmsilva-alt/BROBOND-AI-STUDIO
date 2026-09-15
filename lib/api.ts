/**
 * API client for the studio.
 *
 * Two changes in ETAPA 15, both about not lying to the user:
 *
 * 1. `request` used to swallow every failure — 401, 422, 500, timeout — into the
 *    same `{ data: null, remote: false }`. The UI could not tell "wrong
 *    password" from "server is down", so it always said "offline". Results now
 *    carry `status` and `error`, and `remote` still means "usable data arrived".
 * 2. The base URL is relative and proxied by `next.config.mjs`, so the browser
 *    never hard-codes an origin it may not be able to reach.
 */

export type Job = {
  id: string;
  type: 'image' | 'video';
  // PR002: the wire says `completed` (the internal state stays `complete`).
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  prompt: string;
  progress: number;
  output_url?: string | null;
};

export type ApiResult<T> = {
  data: T;
  /** True only when the API answered successfully with a usable body. */
  remote: boolean;
  /** HTTP status when the server answered at all, even with an error. */
  status?: number;
  /** Human-readable reason. `offline` means no answer was received. */
  error?: string;
};

/**
 * Empty by default: requests go to the same origin and `next.config.mjs`
 * proxies them to FastAPI. Set `NEXT_PUBLIC_API_URL` to talk to another host.
 */
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? '';

const DEFAULT_TIMEOUT_MS = 10000;
const UPLOAD_TIMEOUT_MS = 30000;

import { getAuthToken, setAuthToken } from './memory/project_memory';

// PR002's auth token. Since PR004.1 it is read/written through the Memory
// Adapter's accessors (`lib/memory/project_memory.ts`) — the only file in
// the repo allowed to touch `window.localStorage`. The token is a separate
// contract (auth), not part of `ProjectMemoryState`.

function ok<T>(data: T, status: number): ApiResult<T> {
  return { data, remote: true, status };
}

function failed<T>(error: string, status?: number): ApiResult<T> {
  return { data: null as T, remote: false, status, error };
}

/** Pull a useful message out of a FastAPI error body, which has a known shape. */
async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === 'string') return body.detail;
    if (Array.isArray(body?.detail) && body.detail[0]?.msg) return String(body.detail[0].msg);
    if (body?.detail) return JSON.stringify(body.detail);
  } catch {
    // A non-JSON error body is still an error; fall through to the status text.
  }
  return `API ${response.status} ${response.statusText}`.trim();
}

async function request<T>(path: string, init: RequestInit, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<ApiResult<T>> {
  try {
    const token = getAuthToken();
    const response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init.headers ?? {}) },
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) return failed<T>(await readError(response), response.status);
    // PR003: 204 has no body by design (DELETE) — nothing to parse.
    if (response.status === 204) return ok<T>(null as T, response.status);
    return ok<T>(await response.json() as T, response.status);
  } catch {
    return failed<T>('offline');
  }
}

const get = <T>(path: string) => request<T>(path, { method: 'GET' });
const post = <T>(path: string, payload: unknown) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(payload ?? {}) });

/** Absolute WebSocket URL for a path, derived from wherever the page is served.

 * PR002: the backend authenticates WebSockets through the `token` query
 * parameter — browsers cannot set headers on a WebSocket handshake, so the
 * bearer token stored by `authenticate` rides along here. Without a token the
 * URL is unchanged and the server refuses the socket (1008).
 */
export function wsUrl(path: string): string {
  const base = API_URL || (typeof window !== 'undefined' ? window.location.origin : '');
  const token = getAuthToken();
  return `${base.replace(/^http/, 'ws')}${path}${token ? `${path.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}` : ''}`;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export type AuthUser = { id: string; email: string; name: string };

export async function authenticate(
  path: '/api/v1/auth/login' | '/api/v1/auth/register',
  payload: Record<string, unknown>,
): Promise<ApiResult<{ access_token: string; user: AuthUser }>> {
  const result = await request<{ access_token: string; user: AuthUser }>(path, { method: 'POST', body: JSON.stringify(payload) });
  if (result.remote) setAuthToken(result.data.access_token);
  return result;
}

// ---------------------------------------------------------------------------
// Legacy generation surface
// ---------------------------------------------------------------------------

export function enhancePrompt(payload: Record<string, unknown>) {
  return post<{ original: string; enhanced: string; tokens: string[] }>('/api/v1/prompts/enhance', payload);
}

export function createImageJob(payload: Record<string, unknown>) {
  return post<Job>('/api/v1/generations/images', payload);
}

export function createVideoJob(payload: Record<string, unknown>) {
  return post<Job>('/api/v1/generations/videos', payload);
}

export function cancelJob(jobId: string) {
  return post<Job>(`/api/v1/jobs/${jobId}/cancel`, {});
}

export function createPersona(payload: Record<string, unknown>) {
  return post<Record<string, unknown>>('/api/v1/personas', payload);
}

export function trainPersona(personaId: string, payload: Record<string, unknown>) {
  return post<Record<string, unknown>>(`/api/v1/personas/${personaId}/train`, payload);
}

export function expandStoryboard(payload: Record<string, unknown>) {
  return post<Record<string, unknown>>('/api/v1/storyboards/expand', payload);
}

export type Asset = { id: string; name: string; kind: string; object_key: string; url: string; created_at: string };
export type LoraVersion = { asset_id: string; persona_id: string; name: string; version: string; url: string; created_at: string };

export function listAssets() {
  return get<Asset[]>('/api/v1/assets');
}

export function listPersonaLoras(personaId: string) {
  return get<LoraVersion[]>(`/api/v1/personas/${personaId}/loras`);
}

export async function uploadAsset(file: File): Promise<ApiResult<Asset>> {
  try {
    const token = getAuthToken();
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`${API_URL}/api/v1/assets/upload`, {
      method: 'POST', body: form,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      signal: AbortSignal.timeout(UPLOAD_TIMEOUT_MS),
    });
    if (!response.ok) return failed<Asset>(await readError(response), response.status);
    return ok<Asset>(await response.json() as Asset, response.status);
  } catch {
    return failed<Asset>('offline');
  }
}

// ---------------------------------------------------------------------------
// System — real facts, so the shell stops inventing them
// ---------------------------------------------------------------------------

/** The shape the backend actually returns — there is no card name or VRAM total. */
export type GpuInfo = { available: boolean; backend: string; message?: string };

export type Readiness = {
  ready: boolean;
  inference_ready: boolean;
  media_ready: boolean;
  checks: Record<string, boolean>;
  gpu?: GpuInfo;
};
export type ModelOption = { id: string; label?: string; status?: string; [key: string]: unknown };

export function gpuInfo() {
  return get<GpuInfo>('/api/v1/system/gpu');
}

export function readiness() {
  return get<Readiness>('/api/v1/system/readiness');
}

export function health() {
  return get<Record<string, unknown>>('/api/v1/health');
}

export function imageModels() {
  return get<ModelOption[]>('/api/v1/models/image');
}

export function videoModels() {
  return get<ModelOption[]>('/api/v1/models/video');
}

// ---------------------------------------------------------------------------
// BROBOND CORE — the decision layer the studio is supposed to run on
// ---------------------------------------------------------------------------

export type SceneBeat = {
  number: number;
  objective: string;
  emotion: string;
  camera: string;
  lighting: string;
  motion: string;
  duration_seconds: number;
  shot_code?: string | null;
  reference?: string;
};

/** What `POST /api/v1/core/direct` answers with (ETAPA 7). */
export type DirectorBrief = {
  concept: string;
  format: string;
  logline: string;
  script: string;
  beats: SceneBeat[];
  camera_language: string;
  lighting_language: string;
  music: string;
  pacing: string;
  style_hint: string;
  duration_seconds: number;
  scene_count: number;
  /** Non-empty when the intention could follow more than one language. */
  clarification: string;
};

export function directIntent(payload: {
  intent: string;
  scene_count?: number | null;
  style?: string | null;
  camera_language?: string | null;
  duration_per_scene?: number;
}) {
  return post<DirectorBrief>('/api/v1/core/direct', payload);
}

export type StoryboardFinding = { rule: string; status: string; detail: string };

export type CoreStoryboard = {
  brief: string;
  format: string;
  scene_count: number;
  runtime_seconds: number;
  valid: boolean;
  shots: Array<Record<string, unknown> & { number: number; shot_code: string; shot_name: string; family: string; lens: string; duration_seconds: number }>;
  violations: StoryboardFinding[];
  attention: StoryboardFinding[];
};

export function buildStoryboard(payload: Record<string, unknown>) {
  return post<CoreStoryboard>('/api/v1/core/storyboard', payload);
}

export type TimelineClip = {
  index: number;
  shot_code: string;
  family: string;
  start_seconds: number;
  duration_seconds: number;
  end_seconds: number;
  transition: string;
  source: string;
  rendered: boolean;
};

export type Timeline = {
  format: string;
  clip_count: number;
  duration_seconds: number;
  aspect_ratio: string;
  width: number;
  height: number;
  fps: number;
  complete: boolean;
  rendered_clips: number;
  unrendered_clips: number[];
  valid: boolean;
  violations: StoryboardFinding[];
  warnings: StoryboardFinding[];
  audio: { bed: string; declared: boolean };
  clips: TimelineClip[];
};

export function buildTimeline(payload: Record<string, unknown>) {
  return post<Timeline>('/api/v1/core/timeline', payload);
}

export type QualityReport = {
  kind: string;
  verdict: 'pass' | 'warn' | 'fail';
  ok: boolean;
  structural_score: number;
  checks_run: number;
  checks_passed: number;
  violations: StoryboardFinding[];
  warnings: StoryboardFinding[];
};

export function assessQuality(payload: Record<string, unknown>) {
  return post<QualityReport>('/api/v1/core/quality/assess', payload);
}

export type QualityCapabilities = {
  assesses: string[];
  does_not_assess: string[];
  model_loaded: boolean;
  note: string;
  rules: Array<{ rule: string; status: string; detail: string }>;
};

export function qualityRules() {
  return get<QualityCapabilities>('/api/v1/core/quality/rules');
}

export type ProviderAdapter = {
  id: string;
  label: string;
  kind: 'image' | 'video';
  status: string;
  model_id?: string;
  conditioning?: string[];
};

export function providerAdapters(kind?: 'image' | 'video') {
  return get<{ adapters: ProviderAdapter[]; default_image?: string; default_video?: string }>(
    `/api/v1/core/providers${kind ? `?kind=${kind}` : ''}`,
  );
}

// ---------------------------------------------------------------------------
// PR003 — Persona Memory Engine (persistent persona profiles)
// ---------------------------------------------------------------------------

export type PersonaImageRef = {
  id: string;
  asset_id: string;
  image_type: 'face' | 'body' | 'style' | 'reference';
  order_index: number;
  name?: string | null;
  url?: string | null;
};

export type PersonaWardrobeItem = { id?: string; name: string; category: string; metadata: Record<string, unknown> };
export type PersonaRevision = { id: string; revision: number; notes: Record<string, unknown>; created_by: string; created_at: string };

export type PersonaProfile = {
  id: string;
  workspace_id: string;
  name: string;
  slug: string;
  age: number;
  height: number;
  body_type: string;
  skin_tone: string;
  hair: string;
  beard: string;
  eyes: string;
  voice: string;
  default_style: string;
  lora_id: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
  wardrobe: PersonaWardrobeItem[];
  images: PersonaImageRef[];
  revisions: PersonaRevision[];
};

const patch = <T>(path: string, payload: unknown) =>
  request<T>(path, { method: 'PATCH', body: JSON.stringify(payload ?? {}) });
const del = <T>(path: string) => request<T>(path, { method: 'DELETE' });

export function listPersonaProfiles() {
  return get<PersonaProfile[]>('/api/v1/personas');
}

export function getPersonaProfile(personaId: string) {
  return get<PersonaProfile>(`/api/v1/personas/${personaId}`);
}

export function updatePersonaProfile(personaId: string, payload: Record<string, unknown>) {
  return patch<PersonaProfile>(`/api/v1/personas/${personaId}`, payload);
}

export function deletePersonaProfile(personaId: string) {
  return del<Record<string, unknown>>(`/api/v1/personas/${personaId}`);
}

export function listPersonaImages(personaId: string) {
  return get<PersonaImageRef[]>(`/api/v1/personas/${personaId}/images`);
}

export function addPersonaImage(personaId: string, payload: { asset_id: string; image_type?: 'face' | 'body' | 'style' | 'reference'; order_index?: number }) {
  return post<PersonaImageRef>(`/api/v1/personas/${personaId}/images`, payload);
}
