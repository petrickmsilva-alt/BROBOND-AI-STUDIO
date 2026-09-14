export type Job = {
  id: string;
  type: 'image' | 'video';
  status: 'queued' | 'running' | 'complete' | 'failed' | 'cancelled';
  prompt: string;
  progress: number;
  output_url?: string | null;
};

export type ApiResult<T> = { data: T; remote: boolean };

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

async function request<T>(path: string, init: RequestInit): Promise<ApiResult<T>> {
  try {
    const token = typeof window !== 'undefined' ? window.localStorage.getItem('brobond_access_token') : null;
    const response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init.headers ?? {}) },
      signal: AbortSignal.timeout(2200),
    });
    if (!response.ok) throw new Error(`API ${response.status}`);
    return { data: await response.json() as T, remote: true };
  } catch {
    // Local-first fallback keeps the studio usable while services are offline.
    return { data: null as T, remote: false };
  }
}

export type AuthUser = { id: string; email: string; name: string };

export async function authenticate(path: '/api/v1/auth/login' | '/api/v1/auth/register', payload: Record<string, unknown>): Promise<ApiResult<{ access_token: string; user: AuthUser }>> {
  const result = await request<{ access_token: string; user: AuthUser }>(path, { method: 'POST', body: JSON.stringify(payload) });
  if (result.remote && typeof window !== 'undefined') window.localStorage.setItem('brobond_access_token', result.data.access_token);
  return result;
}

export function enhancePrompt(payload: Record<string, unknown>) {
  return request<{ original: string; enhanced: string; tokens: string[] }>('/api/v1/prompts/enhance', { method: 'POST', body: JSON.stringify(payload) });
}

export function createImageJob(payload: Record<string, unknown>) {
  return request<Job>('/api/v1/generations/images', { method: 'POST', body: JSON.stringify(payload) });
}

export function createVideoJob(payload: Record<string, unknown>) {
  return request<Job>('/api/v1/generations/videos', { method: 'POST', body: JSON.stringify(payload) });
}

export function cancelJob(jobId: string) {
  return request<Job>(`/api/v1/jobs/${jobId}/cancel`, { method: 'POST', body: JSON.stringify({}) });
}

export function createPersona(payload: Record<string, unknown>) {
  return request<Record<string, unknown>>('/api/v1/personas', { method: 'POST', body: JSON.stringify(payload) });
}

export function trainPersona(personaId: string, payload: Record<string, unknown>) {
  return request<Record<string, unknown>>(`/api/v1/personas/${personaId}/train`, { method: 'POST', body: JSON.stringify(payload) });
}

export function expandStoryboard(payload: Record<string, unknown>) {
  return request<Record<string, unknown>>('/api/v1/storyboards/expand', { method: 'POST', body: JSON.stringify(payload) });
}

export type Asset = { id: string; name: string; kind: string; object_key: string; url: string; created_at: string };
export type LoraVersion = { asset_id: string; persona_id: string; name: string; version: string; url: string; created_at: string };

export function listAssets() {
  return request<Asset[]>('/api/v1/assets', { method: 'GET' });
}

export function listPersonaLoras(personaId: string) {
  return request<LoraVersion[]>(`/api/v1/personas/${personaId}/loras`, { method: 'GET' });
}

export async function uploadAsset(file: File): Promise<ApiResult<Asset>> {
  try {
    const token = typeof window !== 'undefined' ? window.localStorage.getItem('brobond_access_token') : null;
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`${API_URL}/api/v1/assets/upload`, {
      method: 'POST', body: form,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      signal: AbortSignal.timeout(8000),
    });
    if (!response.ok) throw new Error(`API ${response.status}`);
    return { data: await response.json() as Asset, remote: true };
  } catch {
    return { data: null as unknown as Asset, remote: false };
  }
}
