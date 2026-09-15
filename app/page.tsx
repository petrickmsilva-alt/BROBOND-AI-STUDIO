'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  API_URL, Asset, AuthUser, DirectorBrief, GpuInfo, Job, LoraVersion, ModelOption, Readiness,
  authenticate, buildStoryboard, cancelJob, createImageJob, createPersona, createVideoJob, directIntent,
  enhancePrompt, gpuInfo, imageModels, listAssets, listPersonaLoras, readiness, trainPersona,
  uploadAsset, videoModels, wsUrl,
} from '../lib/api';
import {
  Aperture, ArrowUpRight, AlertTriangle, Bell, Box, ChevronDown, CircleHelp, Clapperboard,
  Clock3, Download, Folder, Gauge, Grid2X2, Image as ImageIcon, Layers3, Library,
  Menu, MessageSquareText, MoreHorizontal, Move3d, Play, Plus, Search, Settings2,
  Sparkles, Square, UserRound, WandSparkles, X, Zap, LogIn, LockKeyhole, Film, Music4, Timer,
} from 'lucide-react';

const modules = [
  { id: 'director', label: 'Director', icon: MessageSquareText },
  { id: 'dashboard', label: 'Overview', icon: Grid2X2 },
  { id: 'image', label: 'Image generation', icon: ImageIcon },
  { id: 'video', label: 'Video generation', icon: Clapperboard },
  { id: 'persona', label: 'Personas', icon: UserRound },
  { id: 'storyboard', label: 'Storyboard', icon: Layers3 },
  { id: 'assets', label: 'Assets', icon: Library },
];

function Toggle({ on = true }: { on?: boolean }) { return <span className={`toggle ${on ? 'on' : ''}`}><i /></span>; }
function Chip({ children, active = false, onClick }: { children: React.ReactNode; active?: boolean; onClick?: () => void }) { return <button type="button" className={`chip ${active ? 'active' : ''}`} onClick={onClick}>{children}</button>; }

/** A message the user can act on. `offline` is the only case with no detail. */
function Notice({ error, status }: { error?: string; status?: number }) {
  if (!error) return null;
  const offline = error === 'offline';
  return <div className={`notice ${offline ? '' : 'notice-error'}`}>
    <AlertTriangle size={13} />
    <span>{offline ? 'API offline — start FastAPI to run this for real.' : `${error}${status ? ` (${status})` : ''}`}</span>
  </div>;
}

function greetingFor(hour: number): string {
  if (hour < 5) return 'Still up';
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

export default function Home() {
  const [active, setActive] = useState('director');
  const [prompt, setPrompt] = useState('A cinematic portrait of a Brazilian athlete in a brutalist city at blue hour');
  const [generated, setGenerated] = useState(false);
  const [sidebar, setSidebar] = useState(true);
  const [authOpen, setAuthOpen] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [gpu, setGpu] = useState<GpuInfo | null>(null);
  const [system, setSystem] = useState<Readiness | null>(null);
  const [assetCount, setAssetCount] = useState<number | null>(null);
  const [greeting, setGreeting] = useState('Welcome');

  useEffect(() => {
    setGreeting(greetingFor(new Date().getHours()));
    gpuInfo().then(result => { if (result.remote) setGpu(result.data); });
    readiness().then(result => { if (result.remote) setSystem(result.data); });
    listAssets().then(result => { if (result.remote) setAssetCount(result.data.length); });
  }, []);

  const moduleTitle = modules.find(m => m.id === active)?.label ?? 'Overview';
  const create = () => { setActive('director'); };
  const readyChecks = system?.checks ?? {};

  return <main className="app-shell">
    <aside className={`sidebar ${sidebar ? '' : 'collapsed'}`}>
      <div className="brand"><div className="brand-mark"><Aperture size={19} /></div><span>BROBOND</span><small>AI STUDIO</small></div>
      <div className="workspace-select"><div className="workspace-avatar">B</div><div><strong>Personal workspace</strong><span>{API_URL ? 'Remote API' : 'Local instance'}</span></div><ChevronDown size={14} /></div>
      <div className="nav-label">WORKSPACE</div>
      <nav>{modules.map(item => { const Icon = item.icon; return <button key={item.id} className={active === item.id ? 'selected' : ''} onClick={() => setActive(item.id)}><Icon size={18} /><span>{item.label}</span>{item.id === 'director' && <b className="nav-badge">CORE</b>}</button>; })}</nav>
      <div className="nav-label library-label">LIBRARY</div>
      <nav><button onClick={() => setActive('assets')}><Folder size={18} /><span>Projects</span></button><button onClick={() => setActive('assets')}><Library size={18} /><span>All assets</span></button></nav>
      <div className="sidebar-bottom">
        <div className="gpu-card">
          <div className="gpu-head"><span><span className={`status-dot ${gpu?.available ? '' : 'off'}`} /> {gpu === null ? 'Checking…' : gpu.available ? 'GPU ready' : 'No GPU'}</span><MoreHorizontal size={16} /></div>
          <strong>{gpu === null ? 'Reading system' : gpu.available ? 'CUDA device' : (gpu.backend || 'cpu').toUpperCase()}</strong>
          <div className="gpu-meter"><i style={{ width: gpu?.available ? '100%' : '0%' }} /></div>
          <small>{gpu === null ? 'querying /api/v1/system/gpu' : (gpu.message ?? (gpu.available ? 'inference capable' : 'inference disabled'))}</small>
        </div>
        <div className="gpu-card">
          <div className="gpu-head"><span>Readiness</span><span>{system ? `${Object.values(readyChecks).filter(Boolean).length}/${Object.keys(readyChecks).length}` : '—'}</span></div>
          <div className="readiness-list">
            {system === null ? <small>querying…</small> : Object.entries(readyChecks).map(([name, okState]) => (
              <small key={name} className={okState ? 'ok' : 'missing'}>{name}{okState ? '' : ' · missing'}</small>
            ))}
          </div>
        </div>
        <button className="settings" onClick={() => setActive('assets')}><Settings2 size={17} /><span>Settings</span></button>
        <button className="profile" onClick={() => setAuthOpen(true)}><div className="avatar">{user ? user.name.slice(0, 2).toUpperCase() : '—'}</div><span><strong>{user?.name ?? 'Not signed in'}</strong><small>{user ? user.email : 'Sign in to sync'}</small></span><MoreHorizontal size={16} /></button>
      </div>
    </aside>

    <section className="main-area">
      <header className="topbar"><button className="icon-button mobile-menu" onClick={() => setSidebar(!sidebar)}><Menu size={19} /></button><div className="crumb"><span>Workspace</span><span>/</span><strong>{moduleTitle}</strong></div><div className="top-actions"><div className="search"><Search size={16} /><input placeholder="Search projects..." /></div><button className="icon-button"><CircleHelp size={18} /></button><button className="icon-button notification"><Bell size={18} /><i /></button><button className="new-button" onClick={create}><Plus size={17} /> New creation</button></div></header>
      <div className="content">
        {active === 'director' && <DirectorStudio onRenderImage={text => { setPrompt(text); setActive('image'); setGenerated(false); }} />}
        {active === 'dashboard' && <Dashboard onNavigate={setActive} onCreate={create} user={user} greeting={greeting} assetCount={assetCount} system={system} />}
        {active === 'image' && <ImageStudio prompt={prompt} setPrompt={setPrompt} generated={generated} setGenerated={setGenerated} />}
        {active === 'video' && <VideoStudio />}
        {active === 'persona' && <PersonaStudio />}
        {active === 'storyboard' && <Storyboard />}
        {active === 'assets' && <Assets onCounted={setAssetCount} />}
      </div>
    </section>
    {authOpen && <AuthModal user={user} onAuthenticated={setUser} onClose={() => setAuthOpen(false)} />}
  </main>;
}

/**
 * The Director — the front door of the studio.
 *
 * SYSTEM_PROMPT.md is explicit: the user talks to a film director, not to a
 * prompt field. This panel is the only place a plain-language intention enters
 * the product, and it answers with direction — concept, logline, script, beats,
 * music, pacing, duration — never with a prompt string.
 */
function DirectorStudio({ onRenderImage }: { onRenderImage: (prompt: string) => void }) {
  const [intent, setIntent] = useState('');
  const [sceneCount, setSceneCount] = useState<number | null>(null);
  const [brief, setBrief] = useState<DirectorBrief | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [status, setStatus] = useState<number | undefined>();

  const direct = async () => {
    if (!intent.trim()) return;
    setLoading(true); setError(undefined);
    const result = await directIntent({ intent: intent.trim(), scene_count: sceneCount });
    if (result.remote) setBrief(result.data); else setBrief(null);
    setError(result.error); setStatus(result.status);
    setLoading(false);
  };

  const examples = [
    'Quero vender uma camiseta artesanal',
    'Um reels vertical para a loja',
    'Documentário sobre artesãos locais',
    'A product commercial for shoes',
  ];

  return <>
    <PageHeader eyebrow="BROBOND CORE · DIRECTOR" title="Say what you want to exist" description="Describe the intention in plain language. The director answers with concept, script, scenes, cameras, music and duration — you never write a technical prompt.">
      <button className="primary-button" onClick={direct} disabled={loading || !intent.trim()}>{loading ? 'Directing…' : <><Sparkles size={16} /> Direct it</>}</button>
    </PageHeader>

    <div className="director-layout">
      <div className="control-panel">
        <div className="panel-heading"><span>Your intention</span><span className="muted">PT or EN</span></div>
        <textarea value={intent} onChange={event => setIntent(event.target.value)} placeholder="Quero vender uma camiseta artesanal feita à mão…" />
        <div className="prompt-meta"><span>{intent.length} / 1,000</span><button onClick={() => setIntent('')}>Clear</button></div>
        <label>Scenes <span>Optional — the director clamps to 4–8</span>
          <div className="chip-row">
            {[null, 4, 6, 8].map(value => <Chip key={String(value)} active={sceneCount === value} onClick={() => setSceneCount(value)}>{value ?? 'auto'}</Chip>)}
          </div>
        </label>
        <div className="example-row">
          {examples.map(example => <button key={example} className="example-chip" onClick={() => setIntent(example)}>{example}</button>)}
        </div>
        <Notice error={error} status={status} />
      </div>

      <div className="brief-canvas">
        {!brief ? <div className="empty-canvas">
          <div className="empty-icon"><MessageSquareText size={23} /></div>
          <h3>The director is listening</h3>
          <p>State an intention and you will get a brief,<br />not a prompt field.</p>
          {error === 'offline' && <span className="muted">API offline — nothing is being faked here.</span>}
        </div> : <>
          {brief.clarification && <div className="clarification"><MessageSquareText size={15} /><div><strong>The director needs one answer</strong><p>{brief.clarification}</p></div></div>}
          <div className="brief-head">
            <div><span className="brief-format">{brief.format}</span><h2>{brief.concept}</h2><p className="brief-logline">{brief.logline}</p></div>
            <div className="brief-facts">
              <span><Timer size={13} /> {brief.duration_seconds}s</span>
              <span><Film size={13} /> {brief.scene_count} scenes</span>
              <span><Layers3 size={13} /> {brief.style_hint}</span>
            </div>
          </div>
          <div className="brief-body">
            <div className="brief-block"><h4>Script</h4><p>{brief.script}</p></div>
            <div className="brief-facts-row">
              <span><Music4 size={13} /> {brief.music}</span>
              <span><Gauge size={13} /> {brief.pacing}</span>
              <span><Move3d size={13} /> {brief.camera_language}</span>
              <span><Sparkles size={13} /> {brief.lighting_language}</span>
            </div>
            <div className="beat-list">
              {brief.beats.map(beat => <div className="beat" key={beat.number}>
                <span className="beat-number">{String(beat.number).padStart(2, '0')}</span>
                <div><strong>{beat.objective}</strong><p>{beat.camera} · {beat.lighting}</p><small>{beat.emotion} · {beat.duration_seconds}s{beat.shot_code ? ` · ${beat.shot_code}` : ''}</small></div>
              </div>)}
            </div>
            <button className="secondary-button full" onClick={() => onRenderImage(brief.logline)}>Take this to the image studio <ArrowUpRight size={14} /></button>
          </div>
        </>}
      </div>
    </div>
  </>;
}

function AuthModal({ user, onAuthenticated, onClose }: { user: AuthUser | null; onAuthenticated: (user: AuthUser | null) => void; onClose: () => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setMessage('Connecting to workspace...');
    const result = await authenticate(mode === 'login' ? '/api/v1/auth/login' : '/api/v1/auth/register', mode === 'login' ? { email, password } : { email, name, password });
    if (result.remote) { onAuthenticated(result.data.user); onClose(); return; }
    // A rejected login must not be reported as "offline": those are different
    // problems and only one of them is fixed by starting the server.
    if (result.status) { setMessage(result.error ?? `Request failed (${result.status})`); return; }
    if (mode === 'login') { onAuthenticated({ id: 'local', email: email || 'local@brobond.ai', name: name || 'Local session' }); onClose(); }
    else setMessage('API offline. Start FastAPI to create a persistent account.');
  };
  const logout = () => { localStorage.removeItem('brobond_access_token'); onAuthenticated(null); onClose(); };
  return <div className="modal-backdrop" onClick={onClose}><div className="auth-modal" onClick={event => event.stopPropagation()}><button className="modal-close" onClick={onClose}><X size={17} /></button>{user ? <><div className="auth-icon"><LockKeyhole size={20} /></div><h2>{user.name}</h2><p className="auth-subtitle">{user.email}</p><button className="secondary-button full" onClick={logout}>Sign out</button></> : <><div className="auth-icon"><LogIn size={20} /></div><div className="auth-switch"><button className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')}>Sign in</button><button className={mode === 'register' ? 'active' : ''} onClick={() => setMode('register')}>Create account</button></div><h2>{mode === 'login' ? 'Welcome back' : 'Create your workspace'}</h2><p className="auth-subtitle">{mode === 'login' ? 'Sign in to sync your creations and assets.' : 'Start building your private visual studio.'}</p><form onSubmit={submit}>{mode === 'register' && <input value={name} onChange={event => setName(event.target.value)} placeholder="Full name" required />}<input type="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="Email address" required /><input type="password" value={password} onChange={event => setPassword(event.target.value)} placeholder="Password · 8+ characters" minLength={8} required /><button className="primary-button full" type="submit">{mode === 'login' ? 'Sign in' : 'Create account'} <ArrowUpRight size={15} /></button></form>{message && <small className="auth-message">{message}</small>}</>}</div></div>;
}

function PageHeader({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children?: React.ReactNode }) { return <div className="page-header"><div><div className="eyebrow"><Sparkles size={13} /> {eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{children}</div>; }

function Dashboard({ onNavigate, onCreate, user, greeting, assetCount, system }: { onNavigate: (id: string) => void; onCreate: () => void; user: AuthUser | null; greeting: string; assetCount: number | null; system: Readiness | null }) {
  const cards = [
    { id: 'director', title: 'Director', desc: 'State an intention, get direction', icon: MessageSquareText, color: 'purple', stat: 'CORE' },
    { id: 'image', title: 'Image generation', desc: 'Render a directed frame', icon: ImageIcon, color: 'orange', stat: assetCount === null ? '—' : `${assetCount} assets` },
    { id: 'storyboard', title: 'Storyboard', desc: 'Cast a brief into shots', icon: Layers3, color: 'cyan', stat: 'CORE' },
    { id: 'persona', title: 'Persona', desc: 'Build consistent characters', icon: UserRound, color: 'pink', stat: 'LoRA' },
  ];
  return <>
    <PageHeader eyebrow="PERSONAL WORKSPACE" title={`${greeting}${user ? `, ${user.name.split(' ')[0]}` : ''}`} description="What will you direct today?">
      <button className="primary-button" onClick={onCreate}><Plus size={18} /> Talk to the director</button>
    </PageHeader>
    <section className="hero-banner"><div className="hero-copy"><span className="pill"><Zap size={13} /> BROBOND CORE</span><h2>From a thought<br />to a <em>directed film.</em></h2><p>Intention in, direction out. Concept, script, scenes, cameras, music and duration — decided before a single frame is rendered.</p><button className="light-button" onClick={onCreate}>Start with the director <ArrowUpRight size={15} /></button></div><div className="hero-art"><div className="orb orb-one" /><div className="orb orb-two" /><div className="hero-grid" /><span className="art-caption">BROBOND / 001</span></div></section>
    <div className="section-row"><div><h2 className="section-title">Creative tools</h2><p className="section-subtitle">Everything you need to make your next idea real.</p></div></div>
    <div className="tool-grid">{cards.map(card => { const Icon = card.icon; return <button className="tool-card" key={card.id} onClick={() => onNavigate(card.id)}><div className={`tool-icon ${card.color}`}><Icon size={20} /></div><div className="card-arrow"><ArrowUpRight size={16} /></div><h3>{card.title}</h3><p>{card.desc}</p><span className="tool-stat">{card.stat}</span></button>; })}</div>
    <div className="section-row recent-row"><div><h2 className="section-title">System state</h2><p className="section-subtitle">Read from the API, not assumed.</p></div><button className="text-button" onClick={() => onNavigate('assets')}>Open library <ArrowUpRight size={14} /></button></div>
    <div className="state-grid">
      {system === null ? <div className="state-card"><h3>Readiness</h3><p>Querying the API…</p></div> : <>
        <div className="state-card"><h3>Inference</h3><p>{system.inference_ready ? 'Ready' : 'Not available on this host'}</p><span className="tool-stat">{system.gpu?.message ?? system.gpu?.backend ?? 'unknown'}</span></div>
        <div className="state-card"><h3>Media</h3><p>{system.media_ready ? 'FFmpeg present' : 'FFmpeg missing — exports disabled'}</p><span className="tool-stat">{system.media_ready ? 'export capable' : 'no assembly'}</span></div>
        <div className="state-card"><h3>Assets</h3><p>{assetCount === null ? 'Not synced' : `${assetCount} in this workspace`}</p><span className="tool-stat">{assetCount === null ? 'sign in to sync' : 'library'}</span></div>
      </>}
    </div>
  </>;
}

function StudioLayout({ type, children, onGenerate }: { type: string; children: React.ReactNode; onGenerate?: () => void }) { return <><PageHeader eyebrow={`${type.toUpperCase()} WORKSPACE`} title={type === 'Image' ? 'Image generation' : `${type} studio`} description={type === 'Image' ? 'Turn your imagination into high-fidelity visuals.' : 'Compose and direct your next visual sequence.'}><div className="header-actions"><button className="icon-button"><Clock3 size={17} /></button><button className="primary-button" onClick={onGenerate}><Sparkles size={16} /> Generate</button></div></PageHeader>{children}</>; }

function ImageStudio({ prompt, setPrompt, generated, setGenerated }: { prompt: string; setPrompt: (s: string) => void; generated: boolean; setGenerated: (b: boolean) => void }) {
  const [loading, setLoading] = useState(false);
  const [connection, setConnection] = useState('Local preview');
  const [job, setJob] = useState<Job | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | undefined>();
  const [status, setStatus] = useState<number | undefined>();
  const [loras, setLoras] = useState<LoraVersion[]>([]);
  const [selectedLora, setSelectedLora] = useState('');
  const [models, setModels] = useState<ModelOption[]>([]);
  const [model, setModel] = useState('flux-dev');
  const [aspectRatio, setAspectRatio] = useState('16:9');
  const [resolution, setResolution] = useState('1024');
  const [controlnet, setControlnet] = useState('none');
  const [controlScale, setControlScale] = useState(0.8);
  const [ipScale, setIpScale] = useState(0.7);
  const [referenceAssetId, setReferenceAssetId] = useState('');
  const [referenceStatus, setReferenceStatus] = useState('');
  const [enhancing, setEnhancing] = useState(false);

  useEffect(() => {
    imageModels().then(result => { if (result.remote && result.data.length) setModels(result.data); });
    const personaId = typeof window !== 'undefined' ? localStorage.getItem('brobond_persona_id') : null;
    if (personaId) listPersonaLoras(personaId).then(result => { if (result.remote) setLoras(result.data); });
  }, []);

  const handleReference = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]; if (!file) return;
    setReferenceStatus('Uploading reference...'); const result = await uploadAsset(file);
    if (result.remote) { setReferenceAssetId(result.data.id); setReferenceStatus('Reference ready'); }
    else setReferenceStatus(result.error === 'offline' ? 'API offline' : (result.error ?? 'Upload failed'));
    event.target.value = '';
  };

  const enhance = async () => {
    setEnhancing(true); setError(undefined);
    const result = await enhancePrompt({ prompt, style: 'cinematic realism', camera: 'medium shot, 85mm lens' });
    if (result.remote) setPrompt(result.data.enhanced);
    setError(result.error); setStatus(result.status);
    setEnhancing(false);
  };

  useEffect(() => {
    if (!job?.id) return;
    const socket = new WebSocket(wsUrl(`/api/v1/queue/events/${job.id}`));
    socket.onmessage = event => {
      const next = JSON.parse(event.data) as Job;
      setJob(next); setProgress(next.progress);
      setConnection(`Job ${next.status} · ${next.progress}%`);
      // PR002: the wire says `completed` (the internal state stays `complete`).
      if (next.status === 'completed' || next.status === 'failed' || next.status === 'cancelled') setLoading(false);
    };
    socket.onerror = () => setConnection('Job queued · WebSocket unavailable');
    return () => socket.close();
  }, [job?.id]);

  const generate = async () => {
    setLoading(true); setError(undefined); setGenerated(true);
    // Every control on this panel feeds the request. They used to render while
    // the payload carries hard-coded literals, so picking 9:16 produced 16:9.
    const result = await createImageJob({
      prompt, model, aspect_ratio: aspectRatio, resolution, guidance_scale: 7.5, steps: 28,
      lora_id: selectedLora || undefined, controlnet, controlnet_scale: controlScale,
      ip_adapter_scale: ipScale, reference_asset_id: referenceAssetId || undefined,
    });
    if (result.remote) {
      setJob(result.data); setProgress(result.data.progress);
      // PR002: job tracking is authenticated. A job created without a token
      // exists, but its stream is tenant-scoped — say so instead of implying
      // it will update.
      const signedIn = typeof window !== 'undefined' && !!window.localStorage.getItem('brobond_access_token');
      setConnection(signedIn ? `Job ${result.data.id.slice(0, 8)} queued` : 'Job created — sign in to track it');
    }
    else { setJob(null); setConnection(result.error === 'offline' ? 'API offline' : 'Request rejected'); }
    setError(result.error); setStatus(result.status);
    setLoading(false);
  };

  return <StudioLayout type="Image" onGenerate={generate}><div className="studio-grid"><div className="control-panel"><div className="panel-heading"><span>Prompt</span><button className="magic-button" onClick={enhance}><WandSparkles size={14} /> {enhancing ? 'Enhancing...' : 'Enhance'}</button></div><textarea value={prompt} onChange={e => setPrompt(e.target.value)} /><div className="prompt-meta"><span>{prompt.length} / 2,000</span><button onClick={() => setPrompt('')}>Reset</button></div><div className="form-row"><label>Model<select value={model} onChange={event => setModel(event.target.value)}>{(models.length ? models : [{ id: model, label: model, status: 'unknown' }]).map(option => <option key={option.id} value={option.id}>{option.label ?? option.id}{option.status ? ` · ${option.status}` : ''}</option>)}</select></label><label>Aspect ratio<select value={aspectRatio} onChange={event => setAspectRatio(event.target.value)}><option value="16:9">16:9 · Landscape</option><option value="1:1">1:1 · Square</option><option value="9:16">9:16 · Portrait</option></select></label></div><div className="form-row"><label>Resolution<select value={resolution} onChange={event => setResolution(event.target.value)}><option value="1024">1024 · HD</option><option value="2048">2048 · 2K</option></select></label><label>Seed<div className="input-with-action"><input value="Random" readOnly /><button><Aperture size={14} /></button></div></label></div><div className="conditioning-box"><div className="panel-heading"><span>Structure &amp; identity</span><span className="muted">Optional</span></div><label>ControlNet<select value={controlnet} onChange={event => setControlnet(event.target.value)}><option value="none">None</option><option value="pose">OpenPose</option><option value="depth">Depth map</option><option value="canny">Canny edges</option><option value="tile">Tile detail</option></select></label><div className="mini-slider"><span>Control strength <b>{controlScale.toFixed(1)}</b></span><input type="range" min="0" max="2" step="0.1" value={controlScale} onChange={event => setControlScale(Number(event.target.value))} /></div><div className="mini-slider"><span>IP Adapter <b>{ipScale.toFixed(1)}</b></span><input type="range" min="0" max="1" step="0.1" value={ipScale} onChange={event => setIpScale(Number(event.target.value))} /></div></div><div className="panel-footer"><label className="secondary-button lora-select"><Plus size={15} /> {loras.length ? <select value={selectedLora} onChange={event => setSelectedLora(event.target.value)}><option value="">Add LoRA</option>{loras.map(lora => <option value={lora.asset_id} key={lora.asset_id}>{lora.version}</option>)}</select> : 'Add LoRA'}</label><label className="secondary-button upload-label"><ImageIcon size={15} /> {referenceStatus || 'Reference image'}<input type="file" accept="image/*" onChange={handleReference} /></label></div><Notice error={error} status={status} /></div><div className={`generation-canvas ${generated ? 'has-result' : ''}`}>{generated ? <><div className="result-art">{job?.output_url ? <img className="result-image" src={job.output_url} alt={prompt} /> : <div className="result-pending"><Box size={26} /><span>{job?.status === 'failed' ? 'The render failed — no image was produced' : job?.status === 'cancelled' ? 'Cancelled — nothing was produced' : loading || job ? 'Rendering…' : 'No image yet'}</span></div>}{job?.output_url && <span className="result-label">{model} · {aspectRatio}</span>}</div><div className="result-toolbar"><span>{loading ? 'Submitting generation...' : `${connection}${job?.output_url ? ' · ready' : ''}`}{(loading || (job && job.status === 'running')) && <i className="job-progress"><b style={{ width: `${progress}%` }} /></i>}</span><div>{job && (job.status === 'queued' || job.status === 'running') && <button className="cancel-job" onClick={async () => { await cancelJob(job.id); setConnection('Job cancelled'); setLoading(false); }}>Cancel</button>}{job?.output_url && <a className="icon-button" href={job.output_url} target="_blank" rel="noreferrer"><Download size={16} /></a>}</div></div></> : <div className="empty-canvas"><div className="empty-icon"><Sparkles size={23} /></div><h3>Your canvas is empty</h3><p>Describe an image and hit Generate<br />to bring your idea to life.</p><span>The result shown here is always the real render</span></div>}</div></div></StudioLayout>; }

function VideoStudio() {
  const [connection, setConnection] = useState('Ready to render');
  const [job, setJob] = useState<Job | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | undefined>();
  const [status, setStatus] = useState<number | undefined>();
  const [brief, setBrief] = useState('A cinematic slow dolly-in through a futuristic city at night, neon reflections on wet pavement');
  const [duration, setDuration] = useState(5);
  const [aspect, setAspect] = useState('16:9');
  const [models, setModels] = useState<ModelOption[]>([]);
  const [model, setModel] = useState('wan-2.1-t2v');
  const [loras, setLoras] = useState<LoraVersion[]>([]);
  const [selectedLora, setSelectedLora] = useState('');
  const [nativeAudio, setNativeAudio] = useState(true);
  const [cinematicMode, setCinematicMode] = useState(true);

  useEffect(() => {
    videoModels().then(result => { if (result.remote && result.data.length) setModels(result.data); });
    const personaId = typeof window !== 'undefined' ? localStorage.getItem('brobond_persona_id') : null;
    if (personaId) listPersonaLoras(personaId).then(result => { if (result.remote) setLoras(result.data); });
  }, []);

  useEffect(() => {
    if (!job?.id) return;
    const socket = new WebSocket(wsUrl(`/api/v1/queue/events/${job.id}`));
    socket.onmessage = event => {
      const next = JSON.parse(event.data) as Job;
      setJob(next); setProgress(next.progress); setConnection(`Render ${next.status} · ${next.progress}%`);
    };
    socket.onerror = () => setConnection('Render queued · WebSocket unavailable');
    return () => socket.close();
  }, [job?.id]);

  const generate = async () => {
    setConnection('Submitting video job...'); setError(undefined);
    const result = await createVideoJob({ prompt: brief, model, mode: 'text-to-video', duration_seconds: duration, fps: 24, aspect_ratio: aspect, cinematic_mode: cinematicMode, native_audio: nativeAudio, lora_id: selectedLora || undefined });
    if (result.remote) {
      setJob(result.data); setProgress(result.data.progress);
      // PR002: job tracking is authenticated; a tokenless job is not trackable.
      const signedIn = typeof window !== 'undefined' && !!window.localStorage.getItem('brobond_access_token');
      setConnection(signedIn ? `Job ${result.data.id.slice(0, 8)} queued` : 'Job created — sign in to track it');
    }
    else { setJob(null); setConnection(result.error === 'offline' ? 'API offline' : 'Request rejected'); }
    setError(result.error); setStatus(result.status);
  };

  return <StudioLayout type="Video" onGenerate={generate}><div className="video-layout"><div className="control-panel"><div className="tab-row"><button className="active">Text to video</button><button>Image to video</button></div><div className="panel-heading"><span>Describe your shot</span></div><textarea value={brief} onChange={event => setBrief(event.target.value)} /><label>Model<select value={model} onChange={event => setModel(event.target.value)}>{(models.length ? models : [{ id: model, label: model, status: 'unknown' }]).map(option => <option key={option.id} value={option.id}>{option.label ?? option.id}{option.status ? ` · ${option.status}` : ''}</option>)}</select></label><label>Duration <div className="chip-row">{[5, 10, 15].map(value => <Chip key={value} active={duration === value} onClick={() => setDuration(value)}>{value}s</Chip>)}</div></label><label>Format <div className="chip-row">{['16:9', '9:16', '1:1'].map(value => <Chip key={value} active={aspect === value} onClick={() => setAspect(value)}>{value}</Chip>)}</div></label>{loras.length > 0 && <label>Persona LoRA<select value={selectedLora} onChange={event => setSelectedLora(event.target.value)}><option value="">None</option>{loras.map(lora => <option value={lora.asset_id} key={lora.asset_id}>{lora.version}</option>)}</select></label>}<div className="setting-line"><span>Native audio</span><button onClick={() => setNativeAudio(!nativeAudio)}><Toggle on={nativeAudio} /></button></div><div className="setting-line"><span>Cinematic mode</span><button onClick={() => setCinematicMode(!cinematicMode)}><Toggle on={cinematicMode} /></button></div><Notice error={error} status={status} /></div><div className="video-canvas"><div className="video-placeholder">{job?.output_url ? <video className="result-image" src={job.output_url} controls /> : <><div className="video-lines" /><Play size={28} fill="currentColor" /><span>{job?.status === 'failed' ? 'The render failed — no video was produced' : connection}</span></>}{job && (job.status === 'queued' || job.status === 'running') && <><div className="render-progress"><i style={{ width: `${progress}%` }} /></div><button className="cancel-job" onClick={async () => { await cancelJob(job.id); setConnection('Render cancelled'); }}>Cancel render</button></>}</div><div className="timeline"><span>00:00</span><div className="timeline-track"><i style={{ width: `${Math.max(progress, 2)}%` }} /></div><span>{`00:0${duration}`.slice(0, 5)}</span></div></div></div></StudioLayout>; }

function PersonaStudio() {
  const [personaId, setPersonaId] = useState<string | null>(null);
  const [referenceIds, setReferenceIds] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState('Add 20–50 reference images');
  const [runId, setRunId] = useState<string | null>(null);
  const [trainingProgress, setTrainingProgress] = useState(0);
  const [error, setError] = useState<string | undefined>();
  useEffect(() => {
    if (!personaId || !runId) return;
    const socket = new WebSocket(wsUrl(`/api/v1/personas/${personaId}/training/events/${runId}`));
    socket.onmessage = event => { const update = JSON.parse(event.data) as { status: string; progress: number; log: string }; setTrainingProgress(update.progress); setStatus(`${update.log} · ${update.progress}%`); };
    socket.onerror = () => setStatus('Training queued · WebSocket unavailable');
    return () => socket.close();
  }, [personaId, runId]);
  const handleReferences = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (files.length < 20 || files.length > 50) { setStatus('Select between 20 and 50 images'); return; }
    setUploading(true); setStatus(`Uploading 0/${files.length} references...`);
    const uploaded: string[] = [];
    for (let index = 0; index < files.length; index += 1) {
      const result = await uploadAsset(files[index]);
      if (result.remote) uploaded.push(result.data.id);
      setStatus(`Uploading ${index + 1}/${files.length} references...`);
    }
    setReferenceIds(uploaded); setUploading(false);
    setStatus(uploaded.length === files.length ? `${uploaded.length} references ready for training` : 'Some references did not upload — check the API');
    event.target.value = '';
  };
  const startTraining = async () => {
    setStatus('Creating persona...'); setError(undefined);
    const created = personaId ? { remote: true, data: { id: personaId } } : await createPersona({ name: 'Petrick Martins', age: 50, appearance: 'Athletic portrait', eye_color: 'Dark brown', beard: 'Short beard', hair: 'Long, tied back', height_m: 1.85, style: 'Cinematic realism', reference_asset_ids: referenceIds });
    if (!created.remote) { setError(created.error); setStatus(created.error === 'offline' ? 'API offline · start FastAPI to train' : 'Persona rejected'); return; }
    const id = String(created.data.id); setPersonaId(id); localStorage.setItem('brobond_persona_id', id); setStatus('Queuing LoRA training...');
    const trained = await trainPersona(id, { reference_asset_ids: referenceIds, style: 'cinematic realism' });
    if (trained.remote) { setRunId(String(trained.data.run_id)); setTrainingProgress(0); }
    else setError(trained.error);
    setStatus(trained.remote ? 'Training queued · GPU worker pending' : 'Training not queued');
  };
  return <><PageHeader eyebrow="PERSONA LAB" title="Make identity consistent" description="Train a private visual persona for stories that feel unmistakably yours."><label className="primary-button upload-label"><Plus size={17} /> {uploading ? 'Uploading...' : 'Add references'}<input type="file" accept="image/*" multiple onChange={handleReferences} /></label></PageHeader><div className="persona-layout"><div className="persona-card"><div className="persona-cover"><div className="persona-portrait"><UserRound size={42} /></div><span className="trained-badge"><span className={`status-dot ${referenceIds.length >= 20 ? '' : 'off'}`} /> {referenceIds.length >= 20 ? 'Ready' : 'Draft'}</span></div><div className="persona-body"><div><h2>Petrick Martins</h2><p>BROBOND · Athletic portrait</p></div><MoreHorizontal size={18} /><div className="persona-tags"><span>50 years</span><span>1.85m</span><span>Short beard</span><span>Tied hair</span></div><div className="persona-footer"><span><ImageIcon size={14} /> {referenceIds.length} / 20–50 references</span><span>{runId ? 'training run active' : 'no LoRA trained'}</span></div></div></div><div className="training-panel"><div className="panel-heading"><span>Persona details</span><button className="text-button">Edit</button></div>{[['Appearance', 'Athletic, defined features'], ['Eye color', 'Dark brown'], ['Hair', 'Long, tied back'], ['Style', 'Cinematic realism']].map(([a, b]) => <div className="detail-row" key={a}><span>{a}</span><strong>{b}</strong></div>)}<div className="lora-progress"><div><span>LoRA training</span><b>{status}</b></div><div className="progress"><i style={{ width: `${runId ? trainingProgress : Math.min(referenceIds.length / 20 * 100, 100)}%` }} /></div></div><Notice error={error} /><button className="secondary-button full" disabled={uploading || referenceIds.length < 20} onClick={startTraining}><Sparkles size={15} /> Start LoRA training</button></div></div></>;
}

function Storyboard() {
  const [brief, setBrief] = useState('A man walking through a futuristic city, searching for a light beyond the skyline.');
  const [sceneCount, setSceneCount] = useState(4);
  const [scenes, setScenes] = useState<Array<{ number: number; shot_code: string; shot_name: string; family: string; lens: string; duration_seconds: number }>>([]);
  const [format, setFormat] = useState('');
  const [runtime, setRuntime] = useState(0);
  const [findings, setFindings] = useState<Array<{ rule: string; status: string; detail: string }>>([]);
  const [status, setStatus] = useState('Not cast yet');
  const [error, setError] = useState<string | undefined>();
  const generate = async () => {
    setStatus('Casting brief...'); setError(undefined);
    const result = await buildStoryboard({ brief, scene_count: sceneCount, style: 'cinematic realism', camera_language: 'continuous forward movement' });
    if (result.remote) {
      setScenes(result.data.shots);
      setFormat(result.data.format);
      setRuntime(result.data.runtime_seconds);
      setFindings([...result.data.violations, ...result.data.attention]);
      setStatus(`${result.data.scene_count} scenes · ${result.data.runtime_seconds}s${result.data.valid ? '' : ' · has findings'}`);
    } else {
      setStatus('Not cast');
    }
    setError(result.error);
  };
  return <><PageHeader eyebrow="STORYBOARD · CORE" title="Shape the whole story" description="A brief is cast into real shots from the 300-shot library, then checked against the cinematic grammar. Findings are reported, not hidden."><button className="primary-button" onClick={generate}><Sparkles size={16} /> Cast scenes</button></PageHeader><div className="story-input control-panel"><div className="panel-heading"><span>Story brief</span><span className="muted">{format || 'format detected on cast'}</span></div><textarea value={brief} onChange={event => setBrief(event.target.value)} /><div className="story-options"><span>{status}{runtime ? ` · ${runtime}s` : ''}</span><span>·</span><span>{sceneCount} scenes</span><div className="chip-row">{[2, 4, 6, 8].map(value => <Chip key={value} active={sceneCount === value} onClick={() => setSceneCount(value)}>{value}</Chip>)}</div></div><Notice error={error} />{findings.length > 0 && <div className="finding-list">{findings.map((finding, index) => <div className={`finding ${finding.status}`} key={`${finding.rule}-${index}`}><b>{finding.rule}</b><span>{finding.detail}</span></div>)}</div>}</div>{scenes.length === 0 ? <div className="empty-library"><Layers3 size={22} /><h3>No storyboard yet</h3><p>Cast a brief to see the shots the director chose and why.</p></div> : <div className="scene-grid">{scenes.map((scene, i) => <div className="scene-card" key={`${scene.shot_code}-${scene.number}`}><div className={`scene-visual scene-${i % 4}`}><span>SCENE {String(scene.number).padStart(2, '0')}</span><button className="play-overlay"><Play size={13} fill="currentColor" /></button></div><div className="scene-copy"><div><h3>{scene.shot_name}</h3><p>{scene.shot_code} · {scene.family} · {scene.lens} · {scene.duration_seconds}s</p></div><MoreHorizontal size={17} /></div></div>)}</div>}</>;
}

function Assets({ onCounted }: { onCounted: (count: number) => void }) {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [remote, setRemote] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | undefined>();
  useEffect(() => { listAssets().then(result => { setRemote(result.remote); setError(result.error); if (result.remote) { setAssets(result.data); onCounted(result.data.length); } }); }, []);
  const counts = useMemo(() => {
    const by = (kind: string) => assets.filter(asset => asset.kind === kind).length;
    return { all: assets.length, image: by('image'), video: by('video'), audio: by('audio'), lora: by('lora') };
  }, [assets]);
  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true); setError(undefined);
    const result = await uploadAsset(file);
    if (result.remote) { setAssets(current => [result.data, ...current]); setRemote(true); onCounted(assets.length + 1); }
    else setError(result.error);
    setUploading(false);
    event.target.value = '';
  };
  return <><PageHeader eyebrow="LIBRARY" title="Your creative archive" description="Everything you make, in one calm place. Counts are read from the API."><label className="primary-button upload-label"><Plus size={17} /> {uploading ? 'Uploading...' : 'Upload assets'}<input type="file" accept="image/*,video/*,audio/*" onChange={handleUpload} /></label></PageHeader><Notice error={error} /><div className="asset-tabs"><button className="active">All assets <span>{remote ? counts.all : '—'}</span></button><button>Images <span>{remote ? counts.image : '—'}</span></button><button>Videos <span>{remote ? counts.video : '—'}</span></button><button>LoRA <span>{remote ? counts.lora : '—'}</span></button><button>Audio <span>{remote ? counts.audio : '—'}</span></button></div>{!remote ? <div className="empty-library"><Library size={22} /><h3>Library not synced</h3><p>{error === 'offline' ? 'Start FastAPI to load your real assets.' : (error ?? 'Sign in to load your assets.')}</p></div> : assets.length === 0 ? <div className="empty-library"><Library size={22} /><h3>Your library is empty</h3><p>Upload a reference or generate your first asset.</p></div> : <div className="asset-grid">{assets.map((asset, i) => <div className="asset-item" key={asset.id}><div className={`asset-image asset-${i % 6}`} style={asset.url ? { backgroundImage: `url(${asset.url})`, backgroundSize: 'cover', backgroundPosition: 'center' } : undefined}><span>{asset.kind === 'video' ? <Clapperboard size={18} /> : <ImageIcon size={18} />}</span></div><div><strong>{asset.name}</strong><small>{asset.kind} · synced</small></div><MoreHorizontal size={16} /></div>)}</div>}</>;
}
