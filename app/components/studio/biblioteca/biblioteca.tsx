'use client';

/**
 * PR009.7 — Biblioteca Criativa: o orquestrador.
 *
 * Interface apenas. Os quatro fluxos de dados são exatamente os que o
 * módulo já tinha — nenhuma rota, endpoint, token ou tabela muda aqui:
 *
 *   leitura  — `listAssetLibrary()` uma vez por montagem/retry; categoria,
 *              busca e ordenação reaplicam em memória, instantâneos;
 *   ingestão — arrastar/selecionar vira fila, processada em sequência por
 *              `uploadLibraryAsset` (POST /api/v1/assets/upload), com
 *              percentual e bytes/segundo reais do XHR. Ao 201 o item é
 *              prependido à lista: a Biblioteca atualiza sem refresh;
 *   falhas   — chegam tipadas da camada de rede: OFFLINE / CORS / TIMEOUT
 *              viram "sem conexão", o resto vira erro com o texto do servidor;
 *   favoritos— marcação local (cookie nomeado), fora do backend.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { NetworkErrorType, listAssetLibrary, uploadLibraryAsset } from '../../../../lib/api';
import {
  BIBLIOTECA_COPY,
  DEFAULT_VIEW,
  applyView,
  countCategories,
  type BibliotecaView,
  type CategoryId,
  type LibraryAsset,
  type SortId,
} from '../../../../lib/assets/biblioteca';
import { loadFavorites, saveFavorites, toggleFavorite } from '../../../../lib/assets/favorites';
import {
  completeUpload,
  countLibrary,
  createUploadItem,
  failUpload,
  hasActiveUploads,
  markUploading,
  partitionUploads,
  progressUpload,
  uploadKindFor,
  type LibraryCounts,
  type UploadItem,
} from '../../../../lib/assets/library';
import { BibliotecaHeader } from './biblioteca-header';
import { BibliotecaSidebar } from './biblioteca-sidebar';
import { BibliotecaGrid } from './biblioteca-card';
import { BibliotecaDropHint, BibliotecaDropZone, BibliotecaUploadQueue } from './biblioteca-dropzone';
import { BibliotecaPreview } from './biblioteca-preview';
import { BibliotecaState } from './biblioteca-states';

export type BibliotecaProps = {
  /** Reports {all, image, video} so the shell can print counted numbers. */
  onCounted?: (counts: LibraryCounts) => void;
  /** Hands the parent the queue entry point (external Upload buttons). */
  registerEnqueue?: (enqueue: (files: File[]) => void) => void;
};

type LoadStatus = 'loading' | 'ready' | 'offline' | 'error';

let uploadSequence = 0;

export function Biblioteca({ onCounted, registerEnqueue }: BibliotecaProps) {
  const [assets, setAssets] = useState<LibraryAsset[]>([]);
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [detail, setDetail] = useState<string | undefined>();
  const [notice, setNotice] = useState<string | undefined>();
  const [copyNotice, setCopyNotice] = useState<string | undefined>();
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [view, setView] = useState<BibliotecaView>({ ...DEFAULT_VIEW });
  const [preview, setPreview] = useState<LibraryAsset | null>(null);
  const [favorites, setFavorites] = useState<ReadonlySet<string>>(() => new Set<string>());
  const [sheetOpen, setSheetOpen] = useState(false);

  const pendingFiles = useRef(new Map<string, File>());
  const processing = useRef(false);
  const countedRef = useRef(onCounted);
  countedRef.current = onCounted;

  // Favorites are a device preference: read once, on the client.
  useEffect(() => {
    setFavorites(loadFavorites());
  }, []);

  const reportCounts = useCallback((items: LibraryAsset[]) => {
    countedRef.current?.(countLibrary(items));
  }, []);

  const load = useCallback(async () => {
    setStatus('loading');
    setDetail(undefined);
    const result = await listAssetLibrary();
    if (result.remote) {
      setAssets(result.data);
      setStatus('ready');
      reportCounts(result.data);
      return;
    }
    const unreachable =
      result.errorType === NetworkErrorType.OFFLINE ||
      result.errorType === NetworkErrorType.CORS ||
      result.errorType === NetworkErrorType.TIMEOUT;
    setStatus(unreachable ? 'offline' : 'error');
    setDetail(result.error);
    setAssets([]);
  }, [reportCounts]);

  useEffect(() => {
    void load();
  }, [load]);

  const updateUpload = useCallback((id: string, update: (item: UploadItem) => UploadItem) => {
    setUploads(current => current.map(item => (item.id === id ? update(item) : item)));
  }, []);

  const processOne = useCallback(
    async (id: string, file: File) => {
      updateUpload(id, markUploading);
      const result = await uploadLibraryAsset(file, {
        onProgress: progress =>
          updateUpload(id, item => progressUpload(item, progress.loaded, progress.total, progress.bytesPerSecond)),
      });
      pendingFiles.current.delete(id);
      if (result.remote) {
        updateUpload(id, completeUpload);
        // 201 → a Biblioteca se atualiza sozinha, sem refresh.
        setAssets(current => {
          const next = [result.data, ...current];
          reportCounts(next);
          return next;
        });
      } else {
        updateUpload(id, item => failUpload(item, result.error ?? 'Falha no upload'));
      }
    },
    [reportCounts, updateUpload],
  );

  const pumpQueue = useCallback(async () => {
    if (processing.current) return;
    processing.current = true;
    try {
      for (;;) {
        const next = pendingFiles.current.entries().next().value as [string, File] | undefined;
        if (!next) return;
        await processOne(next[0], next[1]);
      }
    } finally {
      processing.current = false;
    }
  }, [processOne]);

  const enqueueFiles = useCallback(
    (files: File[]) => {
      const { accepted, rejected } = partitionUploads(files);
      setNotice(
        rejected.length
          ? `Não adicionados (fora de PNG · JPG · WEBP · MP4 · MOV): ${rejected.map(file => file.name).join(', ')}`
          : undefined,
      );
      accepted.forEach(file => {
        const kind = uploadKindFor(file) as 'image' | 'video';
        uploadSequence += 1;
        const id = `bib-up-${uploadSequence}`;
        pendingFiles.current.set(id, file);
        setUploads(current => [...current, createUploadItem(id, file, kind)]);
      });
      if (accepted.length) void pumpQueue();
    },
    [pumpQueue],
  );

  useEffect(() => {
    registerEnqueue?.(enqueueFiles);
  }, [registerEnqueue, enqueueFiles]);

  const onToggleFavorite = useCallback((asset: LibraryAsset) => {
    setFavorites(current => {
      const next = toggleFavorite(current, asset.id);
      saveFavorites(next);
      return next;
    });
  }, []);

  const onCopyUrl = useCallback((asset: LibraryAsset) => {
    const absolute =
      typeof window !== 'undefined' && asset.url.startsWith('/')
        ? `${window.location.origin}${asset.url}`
        : asset.url;
    const clipboard = typeof navigator !== 'undefined' ? navigator.clipboard : undefined;
    if (clipboard?.writeText) {
      void clipboard.writeText(absolute);
      setCopyNotice('URL copiada.');
    } else {
      // Sem permissão de área de transferência: mostramos a URL em vez de
      // afirmar uma cópia que não aconteceu.
      setCopyNotice(absolute);
    }
  }, []);

  useEffect(() => {
    if (!copyNotice) return undefined;
    const timer = setTimeout(() => setCopyNotice(undefined), 2600);
    return () => clearTimeout(timer);
  }, [copyNotice]);

  const counts = useMemo(() => countCategories(assets, favorites), [assets, favorites]);
  const visible = useMemo(() => applyView(assets, view, favorites), [assets, view, favorites]);
  const busy = hasActiveUploads(uploads);

  const setCategory = (category: CategoryId) => {
    setView(current => ({ ...current, category }));
    setSheetOpen(false);
  };
  const setSearch = (search: string) => setView(current => ({ ...current, search }));
  const setSort = (sort: SortId) => setView(current => ({ ...current, sort }));

  let body: React.ReactNode;
  if (status === 'loading') {
    body = (
      <div className="bib-loading" role="status">
        Lendo a Biblioteca…
      </div>
    );
  } else if (status === 'offline') {
    body = <BibliotecaState state="offline" detail={detail} actionLabel="Tentar novamente" onAction={() => void load()} />;
  } else if (status === 'error') {
    body = <BibliotecaState state="erro" detail={detail} actionLabel="Tentar novamente" onAction={() => void load()} />;
  } else if (assets.length === 0 && busy) {
    body = <BibliotecaState state="enviando" />;
  } else if (assets.length === 0) {
    body = <BibliotecaState state="vazia" />;
  } else if (visible.length === 0) {
    body = (
      <BibliotecaState
        state="filtrada"
        actionLabel="Limpar recorte"
        onAction={() => setView({ ...DEFAULT_VIEW })}
      />
    );
  } else {
    body = (
      <BibliotecaGrid
        assets={visible}
        favorites={favorites}
        onOpen={setPreview}
        onToggleFavorite={onToggleFavorite}
        onCopyUrl={onCopyUrl}
      />
    );
  }

  return (
    <BibliotecaDropZone onFiles={enqueueFiles}>
      <div className="bib-root" data-testid="bib-root">
        <BibliotecaHeader
          search={view.search}
          onSearch={setSearch}
          category={view.category}
          onCategory={setCategory}
          sort={view.sort}
          onSort={setSort}
          onFiles={enqueueFiles}
          onOpenFilters={() => setSheetOpen(true)}
        />

        <div className="bib-body">
          <aside className="bib-aside">
            <BibliotecaSidebar active={view.category} counts={counts} onSelect={setCategory} />
          </aside>

          <section className="bib-main">
            <nav className="bib-breadcrumb" aria-label="Trilha">
              <span>Workspace</span>
              <span aria-hidden="true">/</span>
              <strong>{BIBLIOTECA_COPY.navLabel}</strong>
              <span className="bib-breadcrumb-count">
                {visible.length === assets.length
                  ? `${assets.length} arquivo${assets.length === 1 ? '' : 's'}`
                  : `${visible.length} de ${assets.length}`}
              </span>
            </nav>

            <BibliotecaUploadQueue items={uploads} />

            {notice && (
              <p className="bib-notice" role="status" data-testid="bib-notice">
                {notice}
              </p>
            )}
            {copyNotice && !preview && (
              <p className="bib-notice bib-notice-ok" role="status">
                {copyNotice}
              </p>
            )}

            {status === 'ready' && assets.length > 0 && <BibliotecaDropHint onFiles={enqueueFiles} />}

            {body}
          </section>
        </div>

        {sheetOpen && (
          <div className="bib-sheet" role="dialog" aria-modal="true" aria-label="Filtros da Biblioteca" data-testid="bib-sheet">
            <button type="button" className="bib-sheet-backdrop" aria-label="Fechar filtros" onClick={() => setSheetOpen(false)} />
            <div className="bib-sheet-panel">
              <span className="bib-sheet-grip" aria-hidden="true" />
              <BibliotecaSidebar active={view.category} counts={counts} onSelect={setCategory} compact />
            </div>
          </div>
        )}

        {preview && (
          <BibliotecaPreview
            asset={preview}
            onClose={() => setPreview(null)}
            onCopyUrl={onCopyUrl}
            copyNotice={copyNotice}
          />
        )}
      </div>
    </BibliotecaDropZone>
  );
}
