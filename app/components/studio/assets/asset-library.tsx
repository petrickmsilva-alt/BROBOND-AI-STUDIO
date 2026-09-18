'use client';

/**
 * PR013 (V4.0.1) — the Cinematic Asset Studio orchestrator.
 *
 * Owns the four data flows of the module and nothing else:
 *
 *   read     — `listAssetLibrary()` once per mount/retry; filters and
 *              search re-apply client-side instantly (the backend exposes
 *              the same cuts as query params for API consumers);
 *   ingest   — drops/picks become queue items, processed sequentially via
 *              `uploadLibraryAsset` so each file gets a real percent and
 *              bytes/second readout (XHR progress, not a simulation);
 *   classify — failures arrive typed from the network layer: OFFLINE /
 *              CORS / TIMEOUT render the "no connection" state, everything
 *              else the error state with the server's own text;
 *   counts   — `onCounted` reports {all, image, video} whenever they
 *              change, so the page header prints counted numbers.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { NetworkErrorType, listAssetLibrary, uploadLibraryAsset } from '../../../../lib/api';
import {
  EMPTY_LIBRARY_FILTERS,
  collectFacets,
  completeUpload,
  countLibrary,
  createUploadItem,
  failUpload,
  filterLibrary,
  hasActiveUploads,
  markUploading,
  partitionUploads,
  progressUpload,
  uploadKindFor,
  type LibraryAsset,
  type LibraryCounts,
  type LibraryFilters,
  type UploadItem,
} from '../../../../lib/assets/library';
import { AssetDropZone, UploadQueueList } from './upload-zone';
import { AssetFilterBar } from './asset-filters';
import { AssetGrid } from './asset-grid';
import { AssetPreviewDialog } from './asset-preview';
import { AssetEmptyState } from './asset-empty';

export type AssetLibraryClientProps = {
  onCounted?: (counts: LibraryCounts) => void;
  /** Hands the page the queue entry point (header "Upload" button, tests). */
  registerEnqueue?: (enqueue: (files: File[]) => void) => void;
};

type LoadStatus = 'loading' | 'ready' | 'offline' | 'error';

let uploadSequence = 0;

export function AssetLibraryClient({ onCounted, registerEnqueue }: AssetLibraryClientProps) {
  /** Unknown only while `status === 'loading'`; the list itself is never null. */
  const [assets, setAssets] = useState<LibraryAsset[]>([]);
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [detail, setDetail] = useState<string | undefined>();
  const [notice, setNotice] = useState<string | undefined>();
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [filters, setFilters] = useState<LibraryFilters>({ ...EMPTY_LIBRARY_FILTERS });
  const [preview, setPreview] = useState<LibraryAsset | null>(null);

  /** Files waiting behind their queue ids (the item itself never holds a File). */
  const pendingFiles = useRef(new Map<string, File>());
  const processing = useRef(false);
  const countedRef = useRef(onCounted);
  countedRef.current = onCounted;

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
        onProgress: progress => updateUpload(id, item => progressUpload(item, progress.loaded, progress.total, progress.bytesPerSecond)),
      });
      pendingFiles.current.delete(id);
      if (result.remote) {
        updateUpload(id, completeUpload);
        setAssets(current => {
          const next = [result.data, ...current];
          reportCounts(next);
          return next;
        });
      } else {
        updateUpload(id, item => failUpload(item, result.error ?? 'Upload failed'));
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
      if (rejected.length) {
        setNotice(
          `Not added (type outside PNG · JPG · WEBP · MP4 · MOV): ${rejected.map(file => file.name).join(', ')}`,
        );
      } else {
        setNotice(undefined);
      }
      accepted.forEach(file => {
        // partitionUploads only accepts files uploadKindFor() resolves.
        const kind = uploadKindFor(file) as 'image' | 'video';
        uploadSequence += 1;
        const id = `up-${uploadSequence}`;
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

  const facets = useMemo(() => collectFacets(assets), [assets]);
  const visible = useMemo(() => filterLibrary(assets, filters), [assets, filters]);
  const busy = hasActiveUploads(uploads);

  let body: React.ReactNode = null;
  if (status === 'loading') {
    body = <div className="al-loading" role="status">Reading the library…</div>;
  } else if (status === 'offline') {
    body = <AssetEmptyState state="offline" detail={detail} actionLabel="Try again" onAction={() => void load()} />;
  } else if (status === 'error') {
    body = <AssetEmptyState state="error" detail={detail} actionLabel="Try again" onAction={() => void load()} />;
  } else if (assets.length === 0 && busy) {
    body = <AssetEmptyState state="uploading" />;
  } else if (assets.length === 0) {
    body = <AssetEmptyState state="empty" />;
  } else if (visible.length === 0) {
    body = (
      <AssetEmptyState
        state="filtered"
        actionLabel="Clear filters"
        onAction={() => setFilters({ ...EMPTY_LIBRARY_FILTERS })}
      />
    );
  } else {
    body = <AssetGrid assets={visible} onOpen={setPreview} />;
  }

  return (
    <AssetDropZone onFiles={enqueueFiles}>
      <div className="al-root" data-testid="al-root">
        <UploadQueueList items={uploads} />
        {notice && (
          <div className="al-notice" role="status" data-testid="al-notice">
            {notice}
          </div>
        )}
        {assets.length > 0 && (
          <AssetFilterBar
            filters={filters}
            onChange={setFilters}
            facets={facets}
            resultCount={visible.length}
            totalCount={assets.length}
          />
        )}
        {body}
        {preview && <AssetPreviewDialog asset={preview} onClose={() => setPreview(null)} />}
      </div>
    </AssetDropZone>
  );
}
