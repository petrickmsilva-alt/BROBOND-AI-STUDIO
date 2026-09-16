'use client';

import { useEffect, useState } from 'react';
import { Activity, CheckCircle2, Cpu, FlaskConical, RefreshCcw, XCircle } from 'lucide-react';
import type { ProviderTestResult, UniversalProvider } from '../../../lib/api';
import { failureMessage } from '../../../lib/network/status';
import { listProviders, testProvider } from '../../../lib/api';

const capabilityLabels: Array<[keyof UniversalProvider['capabilities'], string]> = [
  ['supports_image', 'Imagem'],
  ['supports_video', 'Vídeo'],
  ['supports_lora', 'LoRA'],
  ['supports_upscale', 'Upscale'],
  ['supports_seed', 'Seed'],
  ['supports_negative_prompt', 'Negative prompt'],
];

function formatHealthTimestamp(value?: string | null): string {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString('pt-BR', { hour12: false });
}

export default function ProvidersPage() {
  const [providers, setProviders] = useState<UniversalProvider[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [testing, setTesting] = useState<Record<string, boolean>>({});
  const [testResults, setTestResults] = useState<Record<string, ProviderTestResult>>({});
  const [testErrors, setTestErrors] = useState<Record<string, string>>({});

  const load = async () => {
    setLoading(true);
    setError(undefined);
    const result = await listProviders();
    if (result.remote) {
      setProviders(result.data);
    } else {
      setProviders([]);
      setError(failureMessage(result, 'API offline — inicie o FastAPI para testar Providers.'));
    }
    setLoading(false);
  };

  const runRealTest = async (providerId: string) => {
    setTesting(state => ({ ...state, [providerId]: true }));
    setTestErrors(state => ({ ...state, [providerId]: '' }));
    const result = await testProvider(providerId);
    if (result.remote) {
      setTestResults(state => ({ ...state, [providerId]: result.data }));
    } else {
      setTestErrors(state => ({
        ...state,
        [providerId]: failureMessage(result, 'API offline — sem resposta para o teste.'),
      }));
    }
    setTesting(state => ({ ...state, [providerId]: false }));
  };

  useEffect(() => {
    load();
  }, []);

  return <main className="providers-page">
    <section className="providers-hero">
      <div>
        <div className="eyebrow"><Cpu size={13} /> PR009 · REAL AI CONNECTORS</div>
        <h1>Provider universal, sem o Core conhecer modelos.</h1>
        <p>Flux, Wan, Mock e futuros adapters passam pela mesma interface: status, latência, versão, último health e capacidades públicas, sem segredos. Retry, timeout e fallback registrados em telemetria.</p>
      </div>
      <button type="button" className="primary-button" onClick={load} disabled={loading}>
        <RefreshCcw size={15} /> {loading ? 'Testando…' : 'Testar'}
      </button>
    </section>

    {error && <div className="providers-error"><XCircle size={15} /> {error}</div>}

    <section className="provider-grid">
      {providers.map(provider => {
        const available = provider.available ?? provider.status === 'ready';
        const testResult = testResults[provider.id];
        const testError = testErrors[provider.id];
        return <article className="provider-card" key={provider.id}>
          <header>
            <div>
              <span className="provider-kicker">{provider.id}</span>
              <h2>{provider.label}</h2>
            </div>
            <span className={`provider-status ${provider.status}`}>
              {provider.status === 'ready' ? <CheckCircle2 size={14} /> : <Activity size={14} />}
              {provider.status}
            </span>
          </header>
          <dl className="provider-metrics">
            <div><dt>Latência</dt><dd>{provider.latency_ms} ms</dd></div>
            <div><dt>Disponibilidade</dt><dd>{available ? 'Disponível' : 'Indisponível'}</dd></div>
            <div><dt>Versão</dt><dd>{provider.version}</dd></div>
            <div><dt>Último Health</dt><dd>{formatHealthTimestamp(provider.last_health_at)}</dd></div>
            <div><dt>Resolução máx.</dt><dd>{provider.capabilities.max_resolution}</dd></div>
            <div><dt>Prompt budget</dt><dd>{provider.capabilities.prompt_budget}</dd></div>
          </dl>
          <div className="provider-capabilities">
            {capabilityLabels.map(([key, label]) => <span key={key} className={provider.capabilities[key] ? 'on' : ''}>
              {label}
            </span>)}
          </div>
          {provider.reason && <p className="provider-reason">{provider.reason}</p>}
          <div className="provider-test">
            <button
              type="button"
              className="primary-button"
              onClick={() => runRealTest(provider.id)}
              disabled={Boolean(testing[provider.id])}
            >
              <FlaskConical size={14} /> {testing[provider.id] ? 'Executando…' : 'Teste Real'}
            </button>
            {testError && <p className="provider-test-result fail"><XCircle size={13} /> {testError}</p>}
            {testResult && <div className={`provider-test-result ${testResult.success ? 'pass' : 'fail'}`}>
              <span className="provider-test-headline">
                {testResult.success ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
                {testResult.success ? 'Asset gerado' : 'Falhou'} · {testResult.asset_kind || 'sem asset'} · {testResult.attempts} tentativa(s)
              </span>
              <span>latência {testResult.latency_ms} ms · render {testResult.render_time_ms} ms · fila {testResult.queue_time_ms} ms</span>
              {testResult.fallback && <span className="provider-test-fallback">
                fallback → {testResult.executed_provider_id}: {testResult.fallback_reason ?? 'sem motivo registrado'}
              </span>}
              {!testResult.fallback && testResult.error_code && <span>erro: {testResult.error_code}</span>}
            </div>}
          </div>
        </article>;
      })}
    </section>

    {!loading && !error && providers.length === 0 && <div className="empty-canvas providers-empty">
      <div className="empty-icon"><Cpu size={24} /></div>
      <h3>Nenhum Provider registrado</h3>
      <p>O registry universal respondeu, mas ainda não possui adapters registrados.</p>
    </div>}
  </main>;
}
