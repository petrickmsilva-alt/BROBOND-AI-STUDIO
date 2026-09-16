'use client';

/**
 * V3.3 — ExportPanel: the Export Center and duplication, at the campaign level.
 *
 * Export builds the ZIP (manifest, prompts, metadata and every delivered
 * MP4/PNG/thumbnail) and lists each export with its download path. The
 * download goes through the existing authenticated asset route — the file
 * only exists if the export really ran.
 */

import { Copy, Download, PackageOpen } from 'lucide-react';

import type { CampaignExportInfo } from '../../../lib/api';

export default function ExportPanel({
  disabled,
  exports,
  exporting,
  duplicating,
  onExport,
  onDuplicate,
}: {
  disabled: boolean;
  exports: CampaignExportInfo[];
  exporting: boolean;
  duplicating: boolean;
  onExport: () => void;
  onDuplicate: () => void;
}) {
  return (
    <section className="campaign-panel" aria-label="Exportar campanha">
      <header className="campaign-panel-head">
        <h2><PackageOpen size={15} /> Exportar campanha</h2>
        <p>ZIP com manifesto, prompts, metadata e os arquivos entregues — o download usa a rota autenticada de assets.</p>
      </header>

      <div className="campaign-export-actions">
        <button type="button" className="primary-button" onClick={onExport} disabled={disabled || exporting}>
          <PackageOpen size={14} /> {exporting ? 'Empacotando…' : 'Exportar campanha'}
        </button>
        <button type="button" className="secondary-button" onClick={onDuplicate} disabled={disabled || duplicating}>
          <Copy size={14} /> {duplicating ? 'Duplicando…' : 'Duplicar campanha'}
        </button>
      </div>

      {exports.length === 0 ? (
        <p className="campaign-muted">Nenhum export ainda — a campanha pode ser exportada quantas vezes quiser.</p>
      ) : (
        <ul className="campaign-exports">
          {exports.map(exportRow => (
            <li key={exportRow.id}>
              <div>
                <strong>ZIP · {exportRow.file_count} arquivos</strong>
                <small>{exportRow.created_at ? new Date(exportRow.created_at).toLocaleString() : ''} · sha256 {exportRow.sha256.slice(0, 12)}…</small>
              </div>
              <a className="secondary-button" href={exportRow.download_url}>
                <Download size={13} /> Baixar
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
