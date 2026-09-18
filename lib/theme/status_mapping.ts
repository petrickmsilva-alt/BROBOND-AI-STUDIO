/**
 * PR012 — pure mapping helpers from the existing (untouched) API contracts
 * — `Readiness`, `GpuInfo`, `UniversalProvider[]` — onto the presentational
 * `StatusDockIndicator[]` shape the Status Dock renders. No fetch, no
 * side effects: these are pure functions so they can be unit-tested
 * without a network layer, and `app/page.tsx` calls them with data it
 * already has.
 */
import type { GpuInfo, Readiness, UniversalProvider } from '../api';
import type { IndicatorState } from './tokens';
import type { StatusDockIndicator } from '../../components/studio/status-dock';

/** Readiness carries extra deploy-gate booleans (`database`, `storage`)
 * beyond the typed fields — accessed defensively since they are optional
 * on the wire depending on backend version. */
type ReadinessWithGates = Readiness & {
  database?: boolean;
  storage?: boolean;
};

function providerState(providers: UniversalProvider[] | null, id: string): IndicatorState {
  if (providers === null) return 'unknown';
  const provider = providers.find(item => item.id === id || item.id.startsWith(id));
  if (!provider) return 'unknown';
  if (provider.available === true || provider.status === 'ready') return 'online';
  if (provider.status === 'unavailable') return 'degraded';
  return 'offline';
}

export function buildStatusDockIndicators(input: {
  readiness: Readiness | null;
  gpu: GpuInfo | null;
  providers: UniversalProvider[] | null;
  apiOnline: boolean;
}): StatusDockIndicator[] {
  const readiness = input.readiness as ReadinessWithGates | null;

  const apiState: IndicatorState = input.apiOnline ? 'online' : 'offline';
  const dbState: IndicatorState =
    readiness === null ? 'unknown' : (readiness.database ?? readiness.checks?.database ?? true) ? 'online' : 'offline';
  const storageState: IndicatorState =
    readiness === null ? 'unknown' : (readiness.storage ?? readiness.media_ready) ? 'online' : 'degraded';
  const gpuState: IndicatorState = input.gpu === null ? 'unknown' : input.gpu.available ? 'online' : 'degraded';

  return [
    { id: 'api', label: 'API', state: apiState },
    { id: 'database', label: 'Database', state: dbState },
    { id: 'storage', label: 'Storage', state: storageState },
    { id: 'gpu', label: 'GPU', state: gpuState, detail: input.gpu?.message ?? undefined },
    { id: 'flux', label: 'FLUX', state: providerState(input.providers, 'flux') },
    { id: 'wan', label: 'WAN', state: providerState(input.providers, 'wan') },
  ];
}
