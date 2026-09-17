'use client';

/**
 * V3.4 — /studio/quality: the Quality AI Engine console.
 *
 * Pick an asset from the library, run the engine, read the verdict: a radial
 * 0–100 score, a radar over the eight criteria, the detected issues and the
 * suggestions — and the three buttons (Regenerar / Upscale / Aprovar) that
 * RECORD the operator's decision without executing anything, exactly as the
 * sprint demands. Every number on this page states its provenance:
 * `measured` came from the real file/spec, `detector` from an external
 * detector, and unmeasured criteria are listed by name instead of shown as
 * invented zeros.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  Award,
  CheckCircle2,
  Gauge,
  ImageIcon,
  ListChecks,
  RefreshCcw,
  ShieldQuestion,
  Sparkles,
  ThumbsUp,
  Video,
  Wand2,
  XCircle,
} from 'lucide-react';

import type { Asset, QualityConfig, AssetQualityReport } from '../../../lib/api';
import { NetworkErrorType } from '../../../lib/network/request';
import { failureMessage } from '../../../lib/network/status';
import {
  assessAssetQuality,
  getAssetQualityHistory,
  getAssetQualityReport,
  getQualityConfig,
  listAssets,
  recordAssetQualityDecision,
} from '../../../lib/api';

import ScoreRadial from './ScoreRadial';
import CriteriaRadar from './CriteriaRadar';

const CRITERION_LABELS: Record<string, string> = {
  face: 'Rosto',
  hands: 'Mãos',
  eyes: 'Olhos',
  composition: 'Composição',
  lighting: 'Iluminação',
  color: 'Cor',
  motion: 'Movimento',
  prompt_fidelity: 'Fidelidade',
};

const STATUS_LABELS: Record<string, string> = {
  retry: 'Retry recomendado',
  manual_review: 'Revisão manual',
  approved: 'Aprovado',
  masterpiece: 'Masterpiece',
};

const SOURCE_LABELS: Record<string, string> = {
  measured: 'medido',
  detector: 'detector',
};

function describeError(result: { error?: string; errorType?: NetworkErrorType; status?: number }): string {
  if (result.status === 401) return 'Entre com sua conta na tela inicial — o Quality Engine exige identidade.';
  return failureMessage(result, 'API offline — inicie o FastAPI para usar o Quality Engine.');
}

export default function QualityPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [config, setConfig] = useState<QualityConfig | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [report, setReport] = useState<AssetQualityReport | null>(null);
  const [history, setHistory] = useState<AssetQualityReport[]>([]);
  const [prompt, setPrompt] = useState('');
  const [promptCompiled, setPromptCompiled] = useState('');
  const [aspectRatio, setAspectRatio] = useState('16:9');
  const [assessing, setAssessing] = useState(false);
  const [deciding, setDeciding] = useState<string | null>(null);
  const [error, setError] = useState<string | undefined>();
  const [notice, setNotice] = useState<string | undefined>();

  const refreshAssets = useCallback(async (): Promise<Asset[]> => {
    const result = await listAssets();
    if (!result.remote) {
      setError(describeError(result));
      return [];
    }
    setError(undefined);
    const media = result.data.filter(asset => asset.kind === 'image' || asset.kind === 'video');
    setAssets(media);
    return media;
  }, []);

  const openAsset = useCallback(async (assetId: string) => {
    setSelectedId(assetId);
    setReport(null);
    setHistory([]);
    setNotice(undefined);
    const [latest, past] = await Promise.all([
      getAssetQualityReport(assetId),
      getAssetQualityHistory(assetId),
    ]);
    // 404 simply means "never assessed" — an honest empty state, not an error.
    if (latest.remote) setReport(latest.data);
    else if (latest.status && latest.status !== 404) setError(describeError(latest));
    if (past.remote) setHistory(past.data);
  }, []);

  useEffect(() => {
    (async () => {
      const [media, cfg] = await Promise.all([refreshAssets(), getQualityConfig()]);
      if (cfg.remote) setConfig(cfg.data);
      if (media.length > 0) await openAsset(media[0].id);
    })();
    // Load once on mount; the callbacks above are stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleAssess() {
    if (!selectedId) return;
    setAssessing(true);
    setNotice(undefined);
    const result = await assessAssetQuality(selectedId, {
      aspect_ratio: aspectRatio || null,
      prompt_original: prompt,
      prompt_compiled: promptCompiled,
    });
    setAssessing(false);
    if (!result.remote) {
      setError(result.status === 422 ? result.error ?? 'Avaliação recusada.' : describeError(result));
      return;
    }
    setError(undefined);
    setReport(result.data);
    await refreshAssets();
    const past = await getAssetQualityHistory(selectedId);
    if (past.remote) setHistory(past.data);
  }

  async function handleDecision(decision: 'regenerate' | 'upscale' | 'approve') {
    if (!selectedId) return;
    setDeciding(decision);
    const result = await recordAssetQualityDecision(selectedId, decision);
    setDeciding(null);
    if (!result.remote) {
      setError(describeError(result));
      return;
    }
    setError(undefined);
    setReport(result.data);
    setNotice(
      decision === 'regenerate'
        ? 'Decisão registrada: regenerar. Nada foi executado — dispare o render em /studio/render quando quiser.'
        : decision === 'upscale'
          ? 'Decisão registrada: upscale. Nada foi executado — o pipeline de upscale roda por sua conta.'
          : 'Decisão registrada: aprovado.',
    );
  }

  const selected = assets.find(asset => asset.id === selectedId) ?? null;

  return (
    <main className="quality-page">
      <section className="quality-hero">
        <div>
          <h1>Quality AI Engine</h1>
          <p>
            Oito critérios com pesos configuráveis, score 0–100 e um relatório persistente por asset.
            Abaixo de {config?.retry_below ?? 70} o motor recomenda retry, {config?.approved_at ?? 85}+ aprova,{' '}
            {config?.masterpiece_at ?? 95}+ é masterpiece — e toda decisão é sua: o motor recomenda, nunca executa.
            Critérios sem medição aparecem como “não medidos”, não como zeros inventados.
          </p>
        </div>
        <button type="button" className="secondary-button" onClick={() => refreshAssets()}>
          <RefreshCcw size={14} /> Atualizar
        </button>
      </section>

      {error && (
        <div className="quality-error" role="alert">
          <XCircle size={15} /> {error}
        </div>
      )}
      {notice && (
        <div className="quality-notice" role="status">
          <CheckCircle2 size={15} /> {notice}
        </div>
      )}

      <div className="quality-grid">
        <section className="quality-panel quality-assets" aria-label="Assets">
          <header>
            <h2>
              <ListChecks size={15} /> Asset Library
            </h2>
            <p>Imagens e vídeos do workspace, com o badge do último veredito.</p>
          </header>
          {assets.length === 0 ? (
            <p className="quality-muted">
              Nenhum asset de mídia — faça um upload na tela inicial ou renderize em /studio/render.
            </p>
          ) : (
            <ul className="quality-asset-list">
              {assets.map(asset => (
                <li key={asset.id}>
                  <button
                    type="button"
                    className={asset.id === selectedId ? 'selected' : ''}
                    onClick={() => openAsset(asset.id)}
                  >
                    {asset.kind === 'video' ? <Video size={14} /> : <ImageIcon size={14} />}
                    <span>
                      <strong>{asset.name}</strong>
                      <small>
                        {asset.kind}
                        {typeof asset.quality_score === 'number'
                          ? ` · ${asset.quality_score}/100 · ${STATUS_LABELS[asset.quality_status ?? ''] ?? asset.quality_status}`
                          : ' · nunca avaliado'}
                      </small>
                    </span>
                    {typeof asset.quality_score === 'number' && (
                      <b className={`quality-badge quality-badge-${asset.quality_status}`}>{asset.quality_score}</b>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="quality-assess-form">
            <label>
              Aspect ratio pedido
              <select value={aspectRatio} onChange={event => setAspectRatio(event.target.value)}>
                <option value="16:9">16:9</option>
                <option value="9:16">9:16</option>
                <option value="1:1">1:1</option>
                <option value="4:3">4:3</option>
                <option value="3:4">3:4</option>
                <option value="">(não verificar)</option>
              </select>
            </label>
            <label>
              Prompt original (para fidelidade)
              <textarea
                value={prompt}
                onChange={event => setPrompt(event.target.value)}
                placeholder="ex. cinematic portrait golden hour"
              />
            </label>
            <label>
              Prompt compilado
              <textarea
                value={promptCompiled}
                onChange={event => setPromptCompiled(event.target.value)}
                placeholder="a versão expandida pelo PromptCompiler"
              />
            </label>
            <button
              type="button"
              className="primary-button"
              disabled={!selectedId || assessing}
              onClick={handleAssess}
            >
              <Gauge size={14} /> {assessing ? 'Avaliando…' : 'Avaliar qualidade'}
            </button>
          </div>
        </section>

        <section className="quality-panel quality-report" aria-label="Relatório">
          {!selected ? (
            <p className="quality-muted">Selecione um asset para ver ou gerar o relatório.</p>
          ) : !report ? (
            <div className="quality-empty">
              <ShieldQuestion size={26} />
              <h2>{selected.name} nunca foi avaliado</h2>
              <p>
                Rode o motor ao lado. O score virá dos fatos: geometria e pixels lidos do arquivo real,
                fidelidade entre os prompts — e rosto/mãos/olhos só entram com sinais de detector.
              </p>
            </div>
          ) : (
            <>
              <div className="quality-verdict">
                <ScoreRadial score={report.overall_score} status={report.status} />
                <div className="quality-verdict-copy">
                  <b className={`quality-status quality-badge-${report.status}`}>
                    {report.status === 'masterpiece' && <Award size={13} />}
                    {STATUS_LABELS[report.status] ?? report.status}
                  </b>
                  <p>
                    {report.retry_recommended
                      ? 'O motor recomenda regenerar este asset. Nada foi disparado automaticamente.'
                      : report.upscale_recommended
                        ? 'Render aprovado, porém pequeno — o motor recomenda upscale.'
                        : 'Sem ação recomendada além da sua revisão.'}
                  </p>
                  <small>
                    Engine v{report.engine_version} · {new Date(report.created_at).toLocaleString()}
                    {report.operator_decision ? ` · decisão registrada: ${report.operator_decision}` : ''}
                    {history.length > 1 ? ` · ${history.length} avaliações no histórico` : ''}
                  </small>
                  <div className="quality-actions">
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={deciding !== null}
                      onClick={() => handleDecision('regenerate')}
                    >
                      <RefreshCcw size={13} /> {deciding === 'regenerate' ? 'Registrando…' : 'Regenerar'}
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={deciding !== null}
                      onClick={() => handleDecision('upscale')}
                    >
                      <Wand2 size={13} /> {deciding === 'upscale' ? 'Registrando…' : 'Upscale'}
                    </button>
                    <button
                      type="button"
                      className="primary-button"
                      disabled={deciding !== null}
                      onClick={() => handleDecision('approve')}
                    >
                      <ThumbsUp size={13} /> {deciding === 'approve' ? 'Registrando…' : 'Aprovar'}
                    </button>
                  </div>
                </div>
              </div>

              <div className="quality-radar-row">
                <CriteriaRadar criteria={report.criteria} labels={CRITERION_LABELS} />
                <ul className="quality-criteria-list">
                  {report.criteria.map(item => (
                    <li key={item.criterion}>
                      <span>
                        <strong>{CRITERION_LABELS[item.criterion] ?? item.criterion}</strong>
                        <small>
                          peso {item.weight} · {SOURCE_LABELS[item.source] ?? item.source}
                          {item.detail ? ` · ${item.detail}` : ''}
                        </small>
                      </span>
                      <b>{item.score}</b>
                    </li>
                  ))}
                  {report.unmeasured.length > 0 && (
                    <li className="quality-unmeasured">
                      <span>
                        <strong>Não medidos</strong>
                        <small>
                          {report.unmeasured.map(c => CRITERION_LABELS[c] ?? c).join(', ')} — fora da média,
                          nunca zerados.
                        </small>
                      </span>
                    </li>
                  )}
                </ul>
              </div>

              <div className="quality-findings">
                <div>
                  <h3>
                    <XCircle size={14} /> Problemas detectados ({report.issues.length})
                  </h3>
                  {report.issues.length === 0 ? (
                    <p className="quality-muted">Nenhum critério medido abaixo de {config?.issue_below ?? 60}.</p>
                  ) : (
                    <ul>{report.issues.map(issue => <li key={issue}>{issue}</li>)}</ul>
                  )}
                </div>
                <div>
                  <h3>
                    <Sparkles size={14} /> Pontos fortes ({report.strengths.length})
                  </h3>
                  {report.strengths.length === 0 ? (
                    <p className="quality-muted">Nenhum critério medido em {config?.strength_at ?? 85}+.</p>
                  ) : (
                    <ul>{report.strengths.map(strength => <li key={strength}>{strength}</li>)}</ul>
                  )}
                </div>
                <div>
                  <h3>
                    <Wand2 size={14} /> Sugestões ({report.suggestions.length})
                  </h3>
                  {report.suggestions.length === 0 ? (
                    <p className="quality-muted">Nada a sugerir — os critérios medidos estão saudáveis.</p>
                  ) : (
                    <ul>{report.suggestions.map(suggestion => <li key={suggestion}>{suggestion}</li>)}</ul>
                  )}
                </div>
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
