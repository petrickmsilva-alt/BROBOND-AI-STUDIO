'use client';

/**
 * V3.3 — CampaignCalendar: the five-day campaign arc.
 *
 * Dia 1..Dia 5, each with its own focus and CTA, and each carrying a
 * different set of deliverables (Lançamento → Bastidores → Alcance →
 * Conversão → Última chamada). The calendar shows what exists — it never
 * invents a state the API did not report.
 */

import { CalendarDays, Megaphone } from 'lucide-react';

import type { CampaignAsset, CampaignEpisode } from '../../../lib/api';

function mediumTag(asset: CampaignAsset): string {
  const duration = asset.medium === 'video' && asset.duration_seconds ? ` · ${asset.duration_seconds}s` : '';
  return `${asset.medium === 'video' ? 'MP4' : 'PNG'} · ${asset.aspect_ratio} · ${asset.width}×${asset.height}${duration}`;
}

export default function CampaignCalendar({
  episodes,
  assets,
}: {
  episodes: CampaignEpisode[];
  assets: CampaignAsset[];
}) {
  if (episodes.length === 0) {
    return (
      <section className="campaign-panel" aria-label="Calendário">
        <header className="campaign-panel-head">
          <h2><CalendarDays size={15} /> Calendário</h2>
        </header>
        <p className="campaign-muted">Nenhuma campanha selecionada — escreva um briefing e crie a primeira.</p>
      </section>
    );
  }

  return (
    <section className="campaign-panel" aria-label="Calendário">
      <header className="campaign-panel-head">
        <h2><CalendarDays size={15} /> Calendário — 5 dias</h2>
        <p>Cada dia tem um foco, um CTA próprio e um conjunto diferente de ativos.</p>
      </header>
      <ol className="campaign-days">
        {episodes.map(episode => {
          const dayAssets = assets.filter(asset => asset.day === episode.day);
          return (
            <li key={episode.id} className="campaign-day">
              <header>
                <span className="campaign-day-number">Dia {episode.day}</span>
                <strong>{episode.focus}</strong>
                <span className="campaign-day-cta">“{episode.cta}”</span>
              </header>
              {dayAssets.length === 0 ? (
                <p className="campaign-muted">Nenhum ativo neste dia.</p>
              ) : (
                <ul>
                  {dayAssets.map(asset => (
                    <li key={asset.id}>
                      <Megaphone size={13} />
                      <div>
                        <strong>
                          {asset.label}
                          <em className={asset.status === 'delivered' ? 'campaign-status delivered' : 'campaign-status planned'}>
                            {asset.status === 'delivered' ? 'entregue' : 'planejado'}
                          </em>
                        </strong>
                        <small>{mediumTag(asset)}</small>
                        <small className="campaign-asset-cta">CTA: “{asset.cta}”</small>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
