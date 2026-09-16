'use client';

/**
 * V3.3 — /studio/campaigns: the Campaign Builder.
 *
 * One briefing in, a complete campaign out: BriefPanel reads the line and
 * builds the campaign (seven deliverables + five-day timeline + CTA deck),
 * CampaignCalendar shows the arc, CampaignAssets tracks delivery, and
 * ExportPanel packages the ZIP or duplicates the campaign with freshly
 * armed CTAs. This page owns selection state only — every decision lives
 * in the backend, and every panel distinguishes offline, anonymous and
 * rejected instead of lying about any of them.
 */

import { useCallback, useEffect, useState } from 'react';
import { Megaphone, RefreshCcw, XCircle } from 'lucide-react';

import type { Campaign, CampaignDetail } from '../../../lib/api';
import {
  duplicateCampaign,
  exportCampaign,
  getCampaign,
  listCampaigns,
} from '../../../lib/api';

import BriefPanel from './BriefPanel';
import CampaignCalendar from './CampaignCalendar';
import CampaignAssets from './CampaignAssets';
import ExportPanel from './ExportPanel';

function describeError(error: string | undefined, status?: number): string {
  if (error === 'offline') return 'API offline — inicie o FastAPI para usar o Campaign Builder.';
  if (status === 401) return 'Entre com sua conta na tela inicial — campanhas exigem identidade.';
  return error ?? 'Algo falhou.';
}

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CampaignDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [duplicating, setDuplicating] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const refreshList = useCallback(async (): Promise<Campaign[]> => {
    const result = await listCampaigns();
    if (!result.remote) {
      setError(describeError(result.error, result.status));
      return [];
    }
    setError(undefined);
    setCampaigns(result.data);
    return result.data;
  }, []);

  const openCampaign = useCallback(async (campaignId: string) => {
    setLoading(true);
    setSelectedId(campaignId);
    const result = await getCampaign(campaignId);
    setLoading(false);
    if (!result.remote) {
      setDetail(null);
      setError(describeError(result.error, result.status));
      return;
    }
    setError(undefined);
    setDetail(result.data);
  }, []);

  const refreshSelected = useCallback(async () => {
    if (!selectedId) return;
    const result = await getCampaign(selectedId);
    if (result.remote) {
      setError(undefined);
      setDetail(result.data);
    } else {
      setError(describeError(result.error, result.status));
    }
  }, [selectedId]);

  useEffect(() => {
    (async () => {
      const list = await refreshList();
      if (list.length > 0) await openCampaign(list[0].id);
    })();
    // Load once on mount; the callbacks above are stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleCreated(created: CampaignDetail) {
    await refreshList();
    await openCampaign(created.id);
  }

  async function handleExport() {
    if (!selectedId) return;
    setExporting(true);
    const result = await exportCampaign(selectedId);
    setExporting(false);
    if (!result.remote) {
      setError(describeError(result.error, result.status));
      return;
    }
    setError(undefined);
    await refreshSelected();
  }

  async function handleDuplicate() {
    if (!selectedId) return;
    setDuplicating(true);
    const result = await duplicateCampaign(selectedId);
    setDuplicating(false);
    if (!result.remote) {
      setError(describeError(result.error, result.status));
      return;
    }
    setError(undefined);
    await refreshList();
    await openCampaign(result.data.id);
  }

  return (
    <main className="campaigns-page">
      <section className="campaigns-hero">
        <div>
          <h1>Um briefing. Uma campanha completa.</h1>
          <p>O Brief Interpreter lê a linha, o Timeline Builder monta Dia 1..Dia 5 com os sete entregáveis
            (Reel 9:16, Story, Shorts, Banner, Thumbnail, Feed 1:1, YouTube Cover), o deck de CTAs nunca
            repete e o Export Center empacota tudo — sem pedir um novo prompt.</p>
        </div>
        <div className="campaigns-hero-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={async () => {
              const list = await refreshList();
              if (list.length > 0 && !selectedId) await openCampaign(list[0].id);
            }}
          >
            <RefreshCcw size={14} /> Atualizar
          </button>
        </div>
      </section>

      {error && <div className="campaigns-error"><XCircle size={15} /> {error}</div>}

      <BriefPanel onCreated={handleCreated} />

      {campaigns.length > 0 && (
        <section className="campaign-list-wrap" aria-label="Campanhas">
          <h2>Campanhas ({campaigns.length})</h2>
          <ul className="campaign-list">
            {campaigns.map(campaign => (
              <li key={campaign.id}>
                <button
                  type="button"
                  className={campaign.id === selectedId ? 'selected' : ''}
                  onClick={() => openCampaign(campaign.id)}
                >
                  <Megaphone size={14} />
                  <span>
                    <strong>{campaign.name}</strong>
                    <small>
                      {campaign.product} · {campaign.objective} · {campaign.platform}
                      {campaign.primary_cta ? <> · “{campaign.primary_cta}”</> : null}
                    </small>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {detail && (
        <p className="campaign-primary" aria-label="CTA principal">
          CTA principal: “{detail.primary_cta}” — {detail.assets.length} entregáveis · {detail.episodes.length} dias
          {detail.exports.length > 0 ? ` · ${detail.exports.length} export(s)` : ''}
        </p>
      )}

      {loading ? (
        <p className="campaign-muted">Carregando campanha…</p>
      ) : detail ? (
        <div className="campaign-detail-grid">
          <CampaignCalendar episodes={detail.episodes} assets={detail.assets} />
          <div className="campaign-detail-side">
            <CampaignAssets assets={detail.assets} onChanged={refreshSelected} />
            <ExportPanel
              disabled={!selectedId}
              exports={detail.exports}
              exporting={exporting}
              duplicating={duplicating}
              onExport={handleExport}
              onDuplicate={handleDuplicate}
            />
          </div>
        </div>
      ) : (
        <p className="campaign-muted">Nenhuma campanha selecionada — crie a primeira acima.</p>
      )}
    </main>
  );
}
