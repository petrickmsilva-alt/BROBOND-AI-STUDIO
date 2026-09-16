'use client';

import { useEffect, useState } from 'react';
import { Activity, CheckCircle2, Cpu, RefreshCcw, XCircle } from 'lucide-react';
import type { UniversalProvider } from '../../../lib/api';
import { listProviders } from '../../../lib/api';

const capabilityLabels: Array<[keyof UniversalProvider['capabilities'], string]> = [
  ['supports_image', 'Imagem'],
  ['supports_video', 'Vídeo'],
  ['supports_lora', 'LoRA'],
  ['supports_upscale', 'Upscale'],
  ['supports_seed', 'Seed'],
  ['supports_negative_prompt', 'Negative prompt'],
];

export default function ProvidersPage() {
  const [providers, setProviders] = useState<UniversalProvider[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const load = async () => {
    setLoading(true);
    setError(undefined);
    const result = await listProviders();
    if (result.remote) {
      setProviders(result.data);
    } else {
      setProviders([]);
      setError(result.error === 'offline' ? 'API offline — inicie o FastAPI para testar Providers.' : result.error);
    }
    setLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  return <main className="providers-page">
    <section className="providers-hero">
      <div>
        <div className="eyebrow"><Cpu size={13} /> PR007 · GPU PROVIDER ORCHESTRATOR</div>
        <h1>Provider universal, sem o Core conhecer modelos.</h1>
        <p>Flux, Wan, Mock e futuros adapters passam pela mesma interface: status, latência, versão e capacidades públicas, sem segredos.</p>
      </div>
      <button type="button" className="primary-button" onClick={load} disabled={loading}>
        <RefreshCcw size={15} /> {loading ? 'Testando…' : 'Testar'}
      </button>
    </section>

    {error && <div className="providers-error"><XCircle size={15} /> {error}</div>}

    <section className="provider-grid">
      {providers.map(provider => <article className="provider-card" key={provider.id}>
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
          <div><dt>Versão</dt><dd>{provider.version}</dd></div>
          <div><dt>Resolução máx.</dt><dd>{provider.capabilities.max_resolution}</dd></div>
          <div><dt>Prompt budget</dt><dd>{provider.capabilities.prompt_budget}</dd></div>
        </dl>
        <div className="provider-capabilities">
          {capabilityLabels.map(([key, label]) => <span key={key} className={provider.capabilities[key] ? 'on' : ''}>
            {label}
          </span>)}
        </div>
        {provider.reason && <p className="provider-reason">{provider.reason}</p>}
      </article>)}
    </section>

    {!loading && !error && providers.length === 0 && <div className="empty-canvas providers-empty">
      <div className="empty-icon"><Cpu size={24} /></div>
      <h3>Nenhum Provider registrado</h3>
      <p>O registry universal respondeu, mas ainda não possui adapters registrados.</p>
    </div>}
  </main>;
}
