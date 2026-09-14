export type Job = {
  id: string;
  type: 'image' | 'video';
  status: 'queued' | 'running' | 'complete' | 'failed' | 'cancelled';
  prompt: string;
  progress: number;
  output_url?: string | null;
};

export type ApiResult<T> = { data: T; remote: boolean };

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

async function request<T>(path: string, init: RequestInit): Promise<ApiResult<T>> {
  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
      signal: AbortSignal.timeout(2200),
    });
    if (!response.ok) throw new Error(`API ${response.status}`);
    return { data: await response.json() as T, remote: true };
  } catch {
    // Local-first fallback keeps the studio usable while services are offline.
    return { data: null as T, remote: false };
  }
}

export function createImageJob(payload: Record<string, unknown>) {
  return request<Job>('/api/v1/generations/images', { method: 'POST', body: JSON.stringify(payload) });
}

export function createVideoJob(payload: Record<string, unknown>) {
  return request<Job>('/api/v1/generations/videos', { method: 'POST', body: JSON.stringify(payload) });
}

export function createPersona(payload: Record<string, unknown>) {
  return request<Record<string, unknown>>('/api/v1/personas', { method: 'POST', body: JSON.stringify(payload) });
}

export function expandStoryboard(payload: Record<string, unknown>) {
  return request<Record<string, unknown>>('/api/v1/storyboards/expand', { method: 'POST', body: JSON.stringify(payload) });
}
