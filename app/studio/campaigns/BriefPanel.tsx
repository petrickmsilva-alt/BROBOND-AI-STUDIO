'use client';

/**
 * V3.3 — BriefPanel: the campaign's front door.
 *
 * One briefing line in. The panel shows what the Brief Interpreter read
 * (including the fields it had to default, listed as "inferido") and builds
 * the complete campaign on confirm — seven deliverables, five-day timeline,
 * CTA deck — without asking for a single new prompt.
 */

import { useState } from 'react';
import { Sparkles, Wand2 } from 'lucide-react';

import type { CampaignDetail, CampaignInterpretation } from '../../../lib/api';
import { createCampaign, interpretBriefing } from '../../../lib/api';

const EXAMPLES = [
  'Quero lançar a coleção Legacy para o público premium no instagram, vídeos de 15s',
  'Lançar a linha de jaquetas Aurora para executivos no youtube com vídeos de 1 minuto',
  'Vender o tênis Apex 2 no tiktok para o público jovem, 30 segundos',
];

const FIELD_LABELS: Record<string, string> = {
  product: 'Produto',
  product_type: 'Tipo',
  audience: 'Público',
  platform: 'Plataforma',
  objective: 'Objetivo',
  duration_seconds: 'Duração',
};

export default function BriefPanel({
  onCreated,
}: {
  onCreated: (campaign: CampaignDetail) => void;
}) {
  const [briefing, setBriefing] = useState('Quero lançar a coleção Legacy');
  const [name, setName] = useState('');
  const [interpretation, setInterpretation] = useState<CampaignInterpretation | null>(null);
  const [reading, setReading] = useState(false);
  const [building, setBuilding] = useState(false);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  function describeError(error: string | undefined, status?: number): string {
    if (error === 'offline') return 'API offline — inicie o FastAPI para construir a campanha.';
    if (status === 401) return 'Entre com sua conta — campanhas exigem identidade.';
    return error ?? 'Algo falhou.';
  }

  async function read() {
    const text = briefing.trim();
    if (!text) {
      setMessage({ kind: 'error', text: 'Escreva o briefing antes de interpretar.' });
      return;
    }
    setReading(true);
    setMessage(null);
    const result = await interpretBriefing(text);
    setReading(false);
    if (!result.remote) {
      setInterpretation(null);
      setMessage({ kind: 'error', text: describeError(result.error, result.status) });
      return;
    }
    setInterpretation(result.data);
  }

  async function build() {
    const text = briefing.trim();
    if (!text) {
      setMessage({ kind: 'error', text: 'Escreva o briefing antes de criar a campanha.' });
      return;
    }
    setBuilding(true);
    setMessage(null);
    const result = await createCampaign({ briefing: text, name: name.trim() || undefined });
    setBuilding(false);
    if (!result.remote) {
      setMessage({ kind: 'error', text: describeError(result.error, result.status) });
      return;
    }
    setInterpretation(null);
    setMessage({ kind: 'ok', text: `Campanha “${result.data.name}” criada com ${result.data.assets.length} entregáveis.` });
    onCreated(result.data);
  }

  return (
    <section className="campaign-panel" aria-label="Briefing">
      <header className="campaign-panel-head">
        <h2><Wand2 size={15} /> Briefing</h2>
        <p>Uma linha basta: o Brief Interpreter extrai produto, público, plataforma, duração e objetivo — o CTA vem do deck da campanha.</p>
      </header>

      <textarea
        value={briefing}
        onChange={event => setBriefing(event.target.value)}
        placeholder="ex. Quero lançar a coleção Legacy para o público premium no instagram, vídeos de 15s"
        aria-label="Briefing da campanha"
      />

      <div className="campaign-examples">
        {EXAMPLES.map(example => (
          <button key={example} type="button" onClick={() => setBriefing(example)}>
            {example}
          </button>
        ))}
      </div>

      <label className="campaign-name-field">
        Nome da campanha (opcional)
        <input
          value={name}
          onChange={event => setName(event.target.value)}
          placeholder="ex. Legacy SS26 — mantemos o nome lido do briefing"
        />
      </label>

      <div className="campaign-brief-actions">
        <button type="button" className="secondary-button" onClick={read} disabled={reading}>
          <Sparkles size={14} /> {reading ? 'Interpretando…' : 'Interpretar briefing'}
        </button>
        <button type="button" className="primary-button" onClick={build} disabled={building}>
          <Wand2 size={14} /> {building ? 'Construindo campanha…' : 'Criar campanha completa'}
        </button>
      </div>

      {interpretation && (
        <div className="campaign-interpretation" aria-label="Briefing interpretado">
          <strong>{interpretation.name}</strong>
          <dl>
            <div><dt>Produto</dt><dd>{interpretation.product_type ? `${interpretation.product_type} ` : ''}{interpretation.product}</dd></div>
            <div><dt>Público</dt><dd>{interpretation.audience}</dd></div>
            <div><dt>Plataforma</dt><dd>{interpretation.platform}</dd></div>
            <div><dt>Duração</dt><dd>{interpretation.duration_seconds}s</dd></div>
            <div><dt>Objetivo</dt><dd>{interpretation.objective}</dd></div>
            <div><dt>CTA</dt><dd>sorteado do deck da campanha (nunca repete)</dd></div>
          </dl>
          <small>
            Lido do texto: {interpretation.matched.join(', ') || '—'}
            {interpretation.missing.length > 0 && (
              <> · Inferido (default honesto): {interpretation.missing.join(', ')}</>
            )}
          </small>
        </div>
      )}

      {message && (
        <p className={message.kind === 'ok' ? 'campaign-ok' : 'campaign-error'}>{message.text}</p>
      )}
    </section>
  );
}
