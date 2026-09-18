import { describe, expect, it } from 'vitest';
import { buildStatusDockIndicators } from './status_mapping';
import type { GpuInfo, Readiness, UniversalProvider } from '../api';

function provider(overrides: Partial<UniversalProvider> = {}): UniversalProvider {
  return {
    id: 'flux-dev',
    label: 'FLUX',
    status: 'ready',
    latency_ms: 10,
    version: '1.0',
    capabilities: {} as UniversalProvider['capabilities'],
    loaded: true,
    available: true,
    ...overrides,
  };
}

describe('buildStatusDockIndicators', () => {
  it('reports every indicator as unknown when nothing has loaded yet', () => {
    const indicators = buildStatusDockIndicators({ readiness: null, gpu: null, providers: null, apiOnline: false });
    expect(indicators).toHaveLength(6);
    expect(indicators.map(item => item.id)).toEqual(['api', 'database', 'storage', 'gpu', 'flux', 'wan']);
    expect(indicators.find(item => item.id === 'database')?.state).toBe('unknown');
    expect(indicators.find(item => item.id === 'gpu')?.state).toBe('unknown');
    expect(indicators.find(item => item.id === 'flux')?.state).toBe('unknown');
  });

  it('marks api online/offline from the apiOnline flag', () => {
    const online = buildStatusDockIndicators({ readiness: null, gpu: null, providers: null, apiOnline: true });
    const offline = buildStatusDockIndicators({ readiness: null, gpu: null, providers: null, apiOnline: false });
    expect(online.find(i => i.id === 'api')?.state).toBe('online');
    expect(offline.find(i => i.id === 'api')?.state).toBe('offline');
  });

  it('derives database and storage from the readiness payload', () => {
    const readiness: Readiness = { ready: true, inference_ready: true, media_ready: true, checks: { database: true } };
    const indicators = buildStatusDockIndicators({ readiness, gpu: null, providers: null, apiOnline: true });
    expect(indicators.find(i => i.id === 'database')?.state).toBe('online');
    expect(indicators.find(i => i.id === 'storage')?.state).toBe('online');
  });

  it('marks storage degraded when media_ready is false and no explicit storage flag', () => {
    const readiness: Readiness = { ready: false, inference_ready: false, media_ready: false, checks: {} };
    const indicators = buildStatusDockIndicators({ readiness, gpu: null, providers: null, apiOnline: true });
    expect(indicators.find(i => i.id === 'storage')?.state).toBe('degraded');
  });

  it('marks database offline when the explicit database gate is false', () => {
    const readiness = { ready: false, inference_ready: false, media_ready: true, checks: {}, database: false } as Readiness;
    const indicators = buildStatusDockIndicators({ readiness, gpu: null, providers: null, apiOnline: true });
    expect(indicators.find(i => i.id === 'database')?.state).toBe('offline');
  });

  it('maps gpu availability to online/degraded', () => {
    const availableGpu: GpuInfo = { available: true, backend: 'cuda' };
    const noGpu: GpuInfo = { available: false, backend: 'cpu' };
    expect(buildStatusDockIndicators({ readiness: null, gpu: availableGpu, providers: null, apiOnline: true }).find(i => i.id === 'gpu')?.state).toBe('online');
    expect(buildStatusDockIndicators({ readiness: null, gpu: noGpu, providers: null, apiOnline: true }).find(i => i.id === 'gpu')?.state).toBe('degraded');
  });

  it('carries the gpu message as the detail text', () => {
    const gpu: GpuInfo = { available: true, backend: 'cuda', message: 'RTX ready' };
    const indicators = buildStatusDockIndicators({ readiness: null, gpu, providers: null, apiOnline: true });
    expect(indicators.find(i => i.id === 'gpu')?.detail).toBe('RTX ready');
  });

  it('finds FLUX and WAN providers by id prefix and maps their status', () => {
    const providers = [provider({ id: 'flux-dev', status: 'ready', available: true }), provider({ id: 'wan-2.1-t2v', status: 'unavailable', available: false })];
    const indicators = buildStatusDockIndicators({ readiness: null, gpu: null, providers, apiOnline: true });
    expect(indicators.find(i => i.id === 'flux')?.state).toBe('online');
    expect(indicators.find(i => i.id === 'wan')?.state).toBe('degraded');
  });

  it('reports offline for a provider present but not ready and not marked unavailable', () => {
    const providers = [provider({ id: 'flux-dev', status: 'error', available: false })];
    const indicators = buildStatusDockIndicators({ readiness: null, gpu: null, providers, apiOnline: true });
    expect(indicators.find(i => i.id === 'flux')?.state).toBe('offline');
  });

  it('reports unknown for a provider that is not present in the list', () => {
    const providers = [provider({ id: 'flux-dev' })];
    const indicators = buildStatusDockIndicators({ readiness: null, gpu: null, providers, apiOnline: true });
    expect(indicators.find(i => i.id === 'wan')?.state).toBe('unknown');
  });
});
