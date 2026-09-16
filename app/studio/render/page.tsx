'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Ban,
  CheckCircle2,
  Clock3,
  Clapperboard,
  Download,
  Film,
  Image as ImageIcon,
  Loader2,
  Play,
  Plus,
  RefreshCcw,
  Sparkles,
  XCircle,
} from 'lucide-react';
import type {
  ProductionPlan,
  RenderBatch,
  RenderBatchSummary,
  RenderEvent,
  RenderScene,
  UniversalProvider,
} from '../../../lib/api';
import {
  cancelRenderBatch,
  createProductionPlan,
  createRenderBatch,
  getRenderBatch,
  listProviders,
  listRenderBatches,
  retryRenderBatch,
  startRenderBatch,
  wsUrl,
} from '../../../lib/api';

const TERMINAL = new Set(['completed', 'failed', 'cancelled']);

function statusLabel(status: string): string {
  switch (status) {
    case 'queued': return 'Na fila';
    case 'running': return 'Iniciando';
    case 'rendering': return 'Renderizando';
    case 'completed': return 'Concluído';
    case 'failed': return 'Falhou';
    case 'cancelled': return 'Cancelado';
    default: return status;
  }
}

function etaLabel(seconds: number): string {
  if (!seconds || seconds <= 0) return '—';
  if (seconds < 60) return `~${Math.ceil(seconds)}s`;
  return `~${Math.floor(seconds / 60)}min ${Math.ceil(seconds % 60)}s`;
}

function ScenePreview({ scene, kind }: { scene: RenderScene; kind: 'image' | 'video' }) {
  if (!scene.asset) {
    return <div className="render-preview-empty">
      {kind === 'video' ? <Film size={22} /> : <ImageIcon size={22} />}
      <span>{statusLabel(scene.status)}</span>
    </div>;
  }
  if (kind === 'video') {
    return <video className="render-preview-media" src={scene.asset.url} controls preload="metadata" />;
  }
  return <img className="render-preview-media" src={scene.asset.url} alt={`Cena ${scene.scene_number}`} loading="lazy" />;
}

export default function RenderPage() {
  const [intent, setIntent] = useState('');
  const [platform, setPlatform] = useState('cinema');
  const [duration, setDuration] = useState(20);
  const [kind, setKind] = useState<'image' | 'video'>('image');
  const [provider, setProvider] = useState('');
  const [providers, setProviders] = useState<UniversalProvider[]>([]);
  const [aspectRatio, setAspectRatio] = useState<'16:9' | '1:1' | '9:16'>('16:9');
  const [seed, setSeed] = useState('');
  const [plan, setPlan] = useState<ProductionPlan | null>(null);
  const [batches, setBatches] = useState<RenderBatchSummary[]>([]);
  const [batch, setBatch] = useState<RenderBatch | null>(null);
  const [socketState, setSocketState] = useState<'idle' | 'live' | 'closed'>('idle');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const socketRef = useRef<WebSocket | null>(null);

  const refreshQueue = useCallback(async () => {
    const result = await listRenderBatches();
    if (result.remote) setBatches(result.data);
  }, []);

  const refreshBatch = useCallback(async (batchId: string) => {
    const result = await getRenderBatch(batchId);
    if (result.remote) {
      setBatch(result.data);
      return result.data;
    }
    return null;
  }, []);

  useEffect(() => {
    listProviders().then(result => {
      if (result.remote) setProviders(result.data);
    });
    refreshQueue();
  }, [refreshQueue]);

  // Push progress: one socket per selected batch, no polling. The server sends
  // a snapshot, replays history, then streams live events until batch_completed.
  useEffect(() => {
    if (!batch) return;
    if (TERMINAL.has(batch.status)) {
      setSocketState('closed');
      return;
    }
    const socket = new WebSocket(wsUrl(`/ws/render/${batch.batch_id}`));
    socketRef.current = socket;
    socket.onopen = () => setSocketState('live');
    socket.onmessage = (message: MessageEvent) => {
      const payload = JSON.parse(String(message.data)) as RenderEvent;
      if (payload.event === 'snapshot') {
        setBatch(payload.batch);
        return;
      }
      if (payload.event === 'scene_completed' || payload.event === 'batch_completed') {
        void refreshBatch(payload.batch_id).then(() => refreshQueue());
      } else {
        setBatch(current => {
          if (!current || current.batch_id !== payload.batch_id) return current;
          const scenes = current.scenes.map(scene => {
            if (payload.scene_id && scene.scene_id !== payload.scene_id) return scene;
            return {
              ...scene,
              status: (payload.status as RenderScene['status']) ?? scene.status,
              progress: payload.progress ?? scene.progress,
            };
          });
          const progress = Math.floor(scenes.reduce((sum, scene) => sum + scene.progress, 0) / Math.max(1, scenes.length));
          return {
            ...current,
            scenes,
            progress,
            status: payload.event === 'batch_started' ? 'running' : current.status,
            eta_seconds: payload.eta_seconds ?? current.eta_seconds,
          };
        });
      }
      if (payload.event === 'batch_completed') {
        setSocketState('closed');
        socket.close();
      }
    };
    socket.onclose = () => setSocketState(current => (current === 'live' ? 'closed' : current));
    return () => {
      socket.close();
      socketRef.current = null;
    };
  }, [batch?.batch_id, refreshBatch, refreshQueue]); // eslint-disable-line react-hooks/exhaustive-deps

  const createPlan = async () => {
    if (!intent.trim()) return;
    setBusy(true);
    setError(undefined);
    const result = await createProductionPlan({ user_intent: intent.trim(), platform, duration });
    if (result.remote) {
      setPlan(result.data);
    } else {
      setPlan(null);
      setError(result.error === 'offline' ? 'API offline — inicie o FastAPI para criar o plano.' : result.error);
    }
    setBusy(false);
  };

  const renderStoryboard = async () => {
    if (!plan) return;
    setBusy(true);
    setError(undefined);
    const created = await createRenderBatch({
      scenes: plan.shots.map(shot => ({
        scene_number: shot.scene_number,
        title: shot.title,
        objective: shot.objective,
        camera: shot.camera,
        lens: shot.lens,
        lighting: shot.lighting,
        motion: shot.motion,
        duration: shot.duration,
        environment: shot.environment,
        negative_prompt: shot.negative_prompt,
      })),
      kind,
      provider,
      project_id: 'render-studio-project',
      production_plan_id: plan.id,
      persona_id: plan.persona_id,
      style: plan.style,
      mood: plan.mood,
      aspect_ratio: aspectRatio,
      seed: seed.trim() === '' ? null : Number(seed),
    });
    if (!created.remote) {
      setError(created.error === 'offline' ? 'API offline — inicie o FastAPI para renderizar.' : created.error);
      setBusy(false);
      return;
    }
    const started = await startRenderBatch(created.data.batch_id);
    if (!started.remote) {
      setError(started.error);
      setBusy(false);
      return;
    }
    setBatch(created.data);
    await refreshQueue();
    setBusy(false);
  };

  const selectBatch = async (batchId: string) => {
    socketRef.current?.close();
    setSocketState('idle');
    await refreshBatch(batchId);
  };

  const cancel = async (batchId: string) => {
    const result = await cancelRenderBatch(batchId);
    if (result.remote) {
      if (batch?.batch_id === batchId) setBatch(result.data);
      await refreshQueue();
    } else {
      setError(result.error);
    }
  };

  const retry = async (batchId: string) => {
    const result = await retryRenderBatch(batchId);
    if (result.remote) {
      await refreshBatch(batchId);
      await refreshQueue();
    } else {
      setError(result.error);
    }
  };

  const currentScene = batch?.scenes.find(scene => !TERMINAL.has(scene.status)) ?? null;

  return <main className="render-page">
    <section className="render-hero">
      <div>
        <div className="eyebrow"><Clapperboard size={13} /> PR008 · CINEMATIC RENDER ENGINE</div>
        <h1>Storyboard em, cinema out — render real via Executor.</h1>
        <p>O Director planeja, o Scene Renderer compila cada cena em um GenerationSpec e o GenerationExecutor renderiza via Providers. Progresso por push, sem polling.</p>
      </div>
      <span className={`render-live ${socketState}`}>
        <span className="render-live-dot" />{socketState === 'live' ? 'push ao vivo' : socketState === 'closed' ? 'socket fechado' : 'sem socket'}
      </span>
    </section>

    {error && <div className="render-error"><XCircle size={15} /> {error}</div>}

    <section className="render-workbench">
      <div className="control-panel render-plan-panel">
        <div className="panel-heading"><span>Storyboard</span><span className="muted">Director AI</span></div>
        <label className="render-big-field">
          O que renderizar?
          <textarea value={intent} onChange={event => setIntent(event.target.value)} placeholder="Um comercial de relógio de luxo numa cidade neon" />
        </label>
        <div className="render-form-grid">
          <label>Plataforma
            <select value={platform} onChange={event => setPlatform(event.target.value)}>
              <option value="cinema">Cinema</option>
              <option value="youtube">YouTube</option>
              <option value="instagram">Instagram</option>
              <option value="reels">Reels</option>
              <option value="tiktok">TikTok</option>
              <option value="ads">Ads</option>
              <option value="web">Web</option>
            </select>
          </label>
          <label>Duração (s)
            <input type="number" min={6} max={600} value={duration} onChange={event => setDuration(Number(event.target.value))} />
          </label>
          <label>Tipo
            <select value={kind} onChange={event => setKind(event.target.value as 'image' | 'video')}>
              <option value="image">Imagens</option>
              <option value="video">Vídeos</option>
            </select>
          </label>
          <label>Provider
            <select value={provider} onChange={event => setProvider(event.target.value)}>
              <option value="">Padrão da fila</option>
              {providers.map(item => <option key={item.id} value={item.id}>{item.label} · {item.status}</option>)}
            </select>
          </label>
          <label>Aspecto
            <select value={aspectRatio} onChange={event => setAspectRatio(event.target.value as '16:9' | '1:1' | '9:16')}>
              <option value="16:9">16:9</option>
              <option value="1:1">1:1</option>
              <option value="9:16">9:16</option>
            </select>
          </label>
          <label>Seed base
            <input value={seed} inputMode="numeric" placeholder="aleatório" onChange={event => setSeed(event.target.value)} />
          </label>
        </div>
        <button className="secondary-button full" onClick={createPlan} disabled={busy || !intent.trim()}>
          {busy ? <Loader2 size={15} className="spin" /> : <Sparkles size={15} />} Criar storyboard
        </button>
        {plan && <div className="render-plan-summary">
          <strong>{plan.title}</strong>
          <span>{plan.shots.length} cenas · {plan.mood} · {plan.duration}s</span>
        </div>}
        <button className="primary-button full" onClick={renderStoryboard} disabled={busy || !plan}>
          <Play size={15} /> Renderizar storyboard
        </button>
      </div>

      <div className="brief-canvas render-canvas">
        {!batch ? <div className="empty-canvas">
          <div className="empty-icon"><Film size={24} /></div>
          <h3>Nenhum render selecionado</h3>
          <p>Crie um storyboard e renderize, ou escolha um lote na Fila abaixo para acompanhar o progresso.</p>
        </div> : <>
          <div className="brief-head">
            <div>
              <span className="brief-format">{statusLabel(batch.status)} · {batch.kind === 'video' ? 'vídeo' : 'imagem'} · {batch.provider || 'provider padrão'}</span>
              <h2>Lote {batch.batch_id.slice(0, 13)}…</h2>
              <p className="brief-logline">{batch.completed_scenes}/{batch.scene_count} cenas concluídas{batch.failed_scenes > 0 && ` · ${batch.failed_scenes} falharam`}</p>
            </div>
            <div className="brief-facts">
              <span><Clock3 size={13} /> ETA {etaLabel(batch.eta_seconds)}</span>
              <span><Film size={13} /> Cena atual: {currentScene ? `${String(currentScene.scene_number).padStart(2, '0')} · ${currentScene.title}` : '—'}</span>
            </div>
          </div>
          <div className="render-progress-track"><span style={{ width: `${batch.progress}%` }} /></div>
          <div className="render-scene-grid">
            {batch.scenes.map(scene => <article className={`render-scene-card ${scene.status}`} key={scene.scene_id}>
              <ScenePreview scene={scene} kind={batch.kind} />
              <header>
                <span className="render-scene-kicker">Cena {String(scene.scene_number).padStart(2, '0')}</span>
                <h3>{scene.title}</h3>
              </header>
              <div className="render-scene-progress"><span style={{ width: `${scene.progress}%` }} /></div>
              <div className="render-scene-meta">
                <span>{statusLabel(scene.status)} · {scene.progress}%</span>
                {scene.asset && <span>seed {scene.asset.seed ?? '—'}</span>}
              </div>
              {scene.error && <p className="render-scene-error">{scene.error}</p>}
              {scene.asset && <div className="render-scene-actions">
                <a className="secondary-button" href={scene.asset.url} download>Preview</a>
                <a className="secondary-button" href={scene.asset.url} download={`cena-${scene.scene_number}.${batch.kind === 'video' ? 'mp4' : 'png'}`}><Download size={13} /> Download</a>
              </div>}
            </article>)}
          </div>
        </>}
      </div>
    </section>

    <section className="render-queue">
      <div className="render-queue-head">
        <h2><Plus size={15} /> Fila de render</h2>
        <button type="button" className="secondary-button" onClick={() => void refreshQueue()}><RefreshCcw size={13} /> Atualizar</button>
      </div>
      {batches.length === 0 ? <p className="muted">Fila vazia — renders criados aparecem aqui com status, progresso e ações.</p> :
        <div className="render-queue-list">
          {batches.map(row => <div className={`render-queue-row ${row.status} ${batch?.batch_id === row.batch_id ? 'selected' : ''}`} key={row.batch_id}>
            <button type="button" className="render-queue-main" onClick={() => void selectBatch(row.batch_id)}>
              <strong>{row.batch_id.slice(0, 13)}…</strong>
              <span>{row.kind === 'video' ? 'Vídeo' : 'Imagem'} · {row.provider || 'padrão'} · {row.completed_scenes}/{row.scene_count} cenas</span>
              <span className="render-queue-progress"><i style={{ width: `${row.progress}%` }} /></span>
            </button>
            <span className="render-queue-status">
              {row.status === 'completed' ? <CheckCircle2 size={14} /> : row.status === 'failed' ? <XCircle size={14} /> : <Clock3 size={14} />}
              {statusLabel(row.status)} · ETA {etaLabel(row.eta_seconds)}
            </span>
            <span className="render-queue-actions">
              {!TERMINAL.has(row.status) && <button type="button" className="secondary-button" onClick={() => void cancel(row.batch_id)}><Ban size={13} /> Cancelar</button>}
              {TERMINAL.has(row.status) && row.status !== 'completed' && <button type="button" className="secondary-button" onClick={() => void retry(row.batch_id)}><RefreshCcw size={13} /> Repetir</button>}
            </span>
          </div>)}
        </div>}
    </section>
  </main>;
}
