'use client';

/**
 * V3.3 — CampaignAssets: the seven deliverables and their delivery state.
 *
 * An asset is born "planejado" (the prompt, format and CTA are ready for
 * the Render Engine) and becomes "entregue" only when a real stored file
 * is attached — the panel never dresses a plan as a render.
 */

import { useState } from 'react';
import { PackageCheck, Layers } from 'lucide-react';

import type { CampaignAsset } from '../../../lib/api';
import { NetworkErrorType } from '../../../lib/network/request';
import { failureMessage } from '../../../lib/network/status';
import { deliverCampaignAsset } from '../../../lib/api';

function describeError(result: { error?: string; errorType?: NetworkErrorType; status?: number }): string {
  if (result.status === 401) return 'Entre com sua conta — entrega exige identidade.';
  return failureMessage(result, 'API offline — inicie o FastAPI para anexar entregas.');
}

function AssetRow({ asset, onChanged }: { asset: CampaignAsset; onChanged: () => void }) {
  const [outputKey, setOutputKey] = useState('');
  const [thumbnailKey, setThumbnailKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  async function deliver() {
    if (!outputKey.trim() && !thumbnailKey.trim()) {
      setMessage({ kind: 'error', text: 'Informe o object key do arquivo entregue (e/ou do thumbnail).' });
      return;
    }
    setSaving(true);
    setMessage(null);
    const result = await deliverCampaignAsset(asset.campaign_id, asset.id, {
      output_key: outputKey.trim() || undefined,
      thumbnail_key: thumbnailKey.trim() || undefined,
    });
    setSaving(false);
    if (!result.remote) {
      setMessage({ kind: 'error', text: describeError(result) });
      return;
    }
    setMessage({ kind: 'ok', text: 'Entrega anexada — ativo marcado como entregue.' });
    setOutputKey('');
    setThumbnailKey('');
    onChanged();
  }

  return (
    <li className="campaign-asset-row">
      <div className="campaign-asset-info">
        <strong>
          {asset.label}
          <em className={asset.status === 'delivered' ? 'campaign-status delivered' : 'campaign-status planned'}>
            {asset.status === 'delivered' ? 'entregue' : 'planejado'}
          </em>
        </strong>
        <small>Dia {asset.day} · {asset.medium === 'video' ? 'MP4' : 'PNG'} · {asset.aspect_ratio} · {asset.width}×{asset.height}{asset.duration_seconds ? ` · ${asset.duration_seconds}s` : ''}</small>
        <small className="campaign-asset-cta">CTA: “{asset.cta}”</small>
        <code className="campaign-prompt" title={asset.prompt}>{asset.prompt}</code>
        {asset.output_key && <small className="campaign-ok">Arquivo: {asset.output_key}{asset.thumbnail_key ? ` · thumb: ${asset.thumbnail_key}` : ''}</small>}
      </div>
      <div className="campaign-deliver">
        <input
          value={outputKey}
          onChange={event => setOutputKey(event.target.value)}
          placeholder="object key do arquivo (ex. workspace/renders/reel.mp4)"
          aria-label={`Object key entregue para ${asset.label}`}
        />
        <input
          value={thumbnailKey}
          onChange={event => setThumbnailKey(event.target.value)}
          placeholder="object key do thumbnail (opcional)"
          aria-label={`Thumbnail para ${asset.label}`}
        />
        <button type="button" className="secondary-button" onClick={deliver} disabled={saving}>
          <PackageCheck size={14} /> {saving ? 'Anexando…' : 'Anexar entrega'}
        </button>
        {message && (
          <p className={message.kind === 'ok' ? 'campaign-ok' : 'campaign-error'}>{message.text}</p>
        )}
      </div>
    </li>
  );
}

export default function CampaignAssets({
  assets,
  onChanged,
}: {
  assets: CampaignAsset[];
  onChanged: () => void;
}) {
  return (
    <section className="campaign-panel" aria-label="Ativos">
      <header className="campaign-panel-head">
        <h2><Layers size={15} /> Ativos — 7 entregáveis</h2>
        <p>Reel 9:16, Story, Shorts, Banner, Thumbnail, Feed 1:1 e YouTube Cover — gerados do briefing, sem novo prompt.</p>
      </header>
      {assets.length === 0 ? (
        <p className="campaign-muted">Nenhum ativo — crie uma campanha primeiro.</p>
      ) : (
        <ul className="campaign-assets">
          {assets.map(asset => (
            <AssetRow key={asset.id} asset={asset} onChanged={onChanged} />
          ))}
        </ul>
      )}
    </section>
  );
}
