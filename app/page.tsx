'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  API_URL, Asset, AuthUser, DirectorBrief, GpuInfo, Job, LoraVersion, ModelOption, PersonaProfile, Readiness,
  UniversalProvider,
  authMe, buildStoryboard, cancelJob, createImageJob, createPersona, createVideoJob, directIntent,
  enhancePrompt, gpuInfo, imageModels, listAssets, listPersonaLoras, listPersonaProfiles, listProviders, readiness,
  trainPersona, uploadAsset, videoModels, wsUrl,
} from '../lib/api';
import PersonaSelector, { mainImage } from './components/studio/PersonaSelector';
// PR013 — V4.0.1 Cinematic Asset Studio: the whole Assets module is owned by
// these components (upload engine, responsive grid, preview, filters, empty
// states). Only their counts flow back here for the header description.
import { AssetLibraryClient, AssetBrowseButton } from './components/studio/assets';
import type { LibraryCounts } from '../lib/assets/library';
// V3.2.1: failures arrive typed from the network layer — the UI branches on
// NetworkErrorType (never on a bare 'offline' string) and the human text is
// produced by the layer itself (cold start aware).
import { NetworkErrorType } from '../lib/network/request';
import { failureMessage, isUnreachable } from '../lib/network/status';
import PersonaPreview from './components/studio/PersonaPreview';
// PR004.1: components never touch localStorage — project memory flows through
// the Memory Adapter (hook), and the auth/legacy keys through its seam.
import { useProjectMemory } from '../lib/memory/use_project_memory';
import {
  PROJECT_ID,
  getAuthToken,
  setLegacyPersonaId,
} from '../lib/memory/project_memory';
import { getRememberedLogin } from '../lib/memory/remembered_login';
// PR012 — BROBOND UI 4.0: the cinematic shell. These are presentational
// only — they render exactly the navigation / identity / health data this
// file already owns; no FastAPI, Provider, Director or Storyboard code is
// touched by wiring them in.
import { Sidebar, type SidebarGroup } from '../components/studio/sidebar';
import { IdentityBar } from '../components/studio/identity-bar';
import { StatusDock } from '../components/studio/status-dock';
import { HeroWorkspace, type HeroWorkspaceScenePreview } from '../components/studio/hero-workspace';
// PR009.6 — Premium Login Experience: the fullscreen overlay that replaces
// the old auth modal. Presentational only — it renders the same `user`
// state and calls the same `authenticate()` flow this file already owned;
// no FastAPI, Provider, Director or Storyboard code is touched by wiring
// it in.
import { LoginScreen } from '../components/studio/login/login-screen';
import { buildStatusDockIndicators } from '../lib/theme/status_mapping';
import {
  Aperture, ArrowUpRight, AlertTriangle, Bell, Box, ChevronDown, CircleHelp, Clapperboard,
  Clock3, Download, Folder, Gauge, Grid2X2, Image as ImageIcon, Layers3, Library,
  Megaphone, Menu, MessageSquareText, MoreHorizontal, Move3d, Play, Plus, Search, Settings2,
  Sparkles, Square, UserRound, WandSparkles, Zap, Film, Music4, Network, Timer,
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

/** A message the user can act on. Typed failures carry their complete text
 * from the network layer (cold start says "Servidor iniciando…", never
 * "offline"); "no answer" and session-expiry render calm, the API's own
 * errors render as errors. */
function Notice({ error, errorType, status }: { error?: string; errorType?: NetworkErrorType; status?: number }) {
  if (!error) return null;
  const calm = isUnreachable({ errorType }) || errorType === NetworkErrorType.UNAUTHORIZED;
  const text = errorType !== undefined ? error : `${error}${status ? ` (${status})` : ''}`;
  return <div className={`notice ${calm ? '' : 'notice-error'}`}>
    <AlertTriangle size={13} />
    <span>{failureMessage({ error: text, errorType }, 'API offline — start FastAPI to run this for real.')}</span>
  </div>;
}

function greetingFor(hour: number): string {
  if (hour < 5) return 'Still up';
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

export default function Home() {
  const router = useRouter();
  const [active, setActive] = useState('director');
  const [prompt, setPrompt] = useState('A cinematic portrait of a Brazilian athlete in a brutalist city at blue hour');
  const [generated, setGenerated] = useState(false);
  const [sidebar, setSidebar] = useState(true);
  const [authOpen, setAuthOpen] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [gpu, setGpu] = useState<GpuInfo | null>(null);
  const [system, setSystem] = useState<Readiness | null>(null);
  const [assetCount, setAssetCount] = useState<number | null>(null);
  // PR012 — ETAPA 6: Status Dock inputs. `providers` and `apiOnline` are new
  // reads of the same untouched endpoints (`/api/v1/providers`,
  // `readiness()`'s own `.remote` flag) — no new backend surface.
  const [providers, setProviders] = useState<UniversalProvider[] | null>(null);
  const [apiOnline, setApiOnline] = useState(false);
  const [greeting, setGreeting] = useState('Welcome');
  // PR004 — the persona pipeline state is owned by Home so the same identity,
  // style, LoRA and wardrobe selection flow into the Image Studio, the Video
  // Studio and the active-identity chip in the topbar (ETAPA 7).
  const [personas, setPersonas] = useState<PersonaProfile[]>([]);
  const [personasReady, setPersonasReady] = useState(false);
  const [activePersona, setActivePersona] = useState<PersonaProfile | null>(null);
  const [style, setStyle] = useState('');
  const [loras, setLoras] = useState<LoraVersion[]>([]);
  const [selectedLora, setSelectedLora] = useState('');
  const [selectedWardrobe, setSelectedWardrobe] = useState<string[]>([]);
  // PR004.1: the project-level creative controls (camera, aspect, duration)
  // are owned here so the Project Memory contract can persist and restore
  // them — the studios render exactly the same controls as before.
  const [cameraPreset, setCameraPreset] = useState('static');
  const [aspectRatio, setAspectRatio] = useState('16:9');
  const [duration, setDuration] = useState(5);

  // PR004.1 — Project Memory: the component knows only the hook (which
  // knows only the Memory Adapter). No storage key, no localStorage, no
  // serialization in this file.
  const { memory, save: saveMemory } = useProjectMemory(PROJECT_ID);
  const restoredRef = useRef(false);

  const loadLoras = (personaId: string, preferred?: string) => {
    listPersonaLoras(personaId).then(result => {
      if (!result.remote) return;
      setLoras(result.data);
      // PR004 (ETAPA 6): the project's last LoRA choice is restored when it
      // still exists for the persona.
      if (preferred && result.data.some(item => item.asset_id === preferred)) setSelectedLora(preferred);
    });
  };

  useEffect(() => {
    setGreeting(greetingFor(new Date().getHours()));
    gpuInfo().then(result => { if (result.remote) setGpu(result.data); });
    readiness().then(result => { setApiOnline(result.remote); if (result.remote) setSystem(result.data); });
    listAssets().then(result => { if (result.remote) setAssetCount(result.data.length); });
    listProviders().then(result => { if (result.remote) setProviders(result.data); });
    listPersonaProfiles().then(result => {
      if (result.remote) setPersonas(result.data);
      setPersonasReady(true);
    });
  }, []);

  // PR009.6 — "Lembrar de mim" (30 days): a remembered login restores the
  // session on load. With a token it reads the profile through the endpoint
  // the backend already serves (GET /api/v1/auth/me); a local session
  // (signed in while the API was unreachable) restores from the remembered
  // profile itself. A rejected token signs out honestly instead of faking
  // a session — only an unreachable API falls back to the local profile.
  useEffect(() => {
    const remembered = getRememberedLogin();
    if (!remembered) return;
    if (!getAuthToken()) {
      setUser({ id: 'local', email: remembered.email, name: remembered.name });
      return;
    }
    authMe().then(result => {
      if (result.remote) setUser(result.data);
      else if (!result.status) setUser({ id: 'local', email: remembered.email, name: remembered.name });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one-shot restore
  }, []);

  // PR004.1: restore the project memory once, when both the memory (loaded
  // synchronously by the hook) and the persona catalog are available.
  useEffect(() => {
    if (!memory || !personasReady || restoredRef.current) return;
    restoredRef.current = true;
    const saved = memory.personaId ? personas.find(persona => persona.id === memory.personaId) : null;
    if (saved) {
      setActivePersona(saved);
      setStyle(memory.styleId || saved.default_style);
      setSelectedWardrobe((memory.wardrobeId ? memory.wardrobeId.split(',') : []).filter(name => name && saved.wardrobe.some(item => item.name === name)));
      loadLoras(saved.id, memory.loraId ?? undefined);
    }
    if (memory.cameraPreset) setCameraPreset(memory.cameraPreset);
    if (memory.aspectRatio) setAspectRatio(memory.aspectRatio);
    if (memory.duration) setDuration(memory.duration);
    if (memory.lastPrompt) setPrompt(memory.lastPrompt);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one-shot restore
  }, [memory, personasReady]);

  // PR004.1: the creative state is persisted on every change (official
  // ProjectMemoryState — the exact object the future PostgreSQL store
  // will serve), so reopening the project restores it automatically.
  useEffect(() => {
    saveMemory({
      workspaceId: activePersona?.workspace_id ?? null,
      personaId: activePersona?.id ?? null,
      wardrobeId: selectedWardrobe.length ? selectedWardrobe.join(',') : null,
      styleId: style || null,
      loraId: selectedLora || null,
      cameraPreset,
      aspectRatio,
      lastPrompt: prompt || null,
      lastPlatform: active === 'video' ? 'video' : active === 'image' ? 'image' : null,
      duration,
    });
  }, [activePersona, style, selectedLora, selectedWardrobe, cameraPreset, aspectRatio, prompt, active, duration, saveMemory]);

  const selectPersona = (persona: PersonaProfile | null) => {
    setActivePersona(persona);
    // ETAPA 5: the user only chooses the Persona — the style follows the
    // persona's default (the field stays editable afterwards).
    if (persona) setStyle(persona.default_style);
    // Wardrobe names belong to a specific persona: switching identity resets
    // the selection instead of carrying stale names into the new identity.
    setSelectedWardrobe([]);
    if (persona) loadLoras(persona.id); else { setLoras([]); setSelectedLora(''); }
  };

  const toggleWardrobe = (name: string) => {
    setSelectedWardrobe(current => current.includes(name) ? current.filter(item => item !== name) : [...current, name]);
  };

  const moduleTitle = modules.find(m => m.id === active)?.label ?? 'Overview';
  const create = () => { setActive('director'); };

  // PR012 — ETAPA 3: the Sidebar Premium groups. CREATE / STUDIO / LIBRARY
  // exactly as specced; badges are limited to GPU/SQL/AI by the component
  // itself (`isAllowedBadge`), so anything else passed here is dropped —
  // GRAPH/V3.2/V3.3/V3.4 no longer render.
  const sidebarGroups: SidebarGroup[] = [
    {
      id: 'create',
      label: 'Create',
      items: [
        { id: 'director', label: 'Director', icon: MessageSquareText, badge: 'AI' },
        { id: 'storyboard', label: 'Storyboard', icon: Layers3 },
        { id: 'render', label: 'Render Queue', icon: Film },
      ],
    },
    {
      id: 'studio',
      label: 'Studio',
      items: [
        { id: 'persona', label: 'Personas', icon: UserRound, badge: 'SQL' },
        { id: 'image', label: 'Image', icon: ImageIcon },
        { id: 'video', label: 'Video', icon: Clapperboard, badge: 'GPU' },
        { id: 'campaigns', label: 'Campaigns', icon: Megaphone },
      ],
    },
    {
      id: 'library',
      label: 'Library',
      items: [
        { id: 'assets', label: 'Assets', icon: Library },
        { id: 'knowledge', label: 'Knowledge', icon: Network },
        { id: 'continuity', label: 'Continuity', icon: Film },
        { id: 'quality', label: 'Quality', icon: Gauge },
      ],
    },
  ];

  const sidebarRoutes: Record<string, string> = {
    render: '/studio/render',
    campaigns: '/studio/campaigns',
    knowledge: '/studio/knowledge',
    continuity: '/studio/continuity',
    quality: '/studio/quality',
  };

  const handleSidebarNavigate = (id: string) => {
    const route = sidebarRoutes[id];
    if (route) { router.push(route); return; }
    setActive(id);
  };

  // PR012 — ETAPA 6: the Status Dock replaces the old sidebar "Readiness"
  // block. `buildStatusDockIndicators` is a pure mapping over the exact
  // same `readiness()` / `gpuInfo()` / `listProviders()` reads above.
  const statusDockIndicators = buildStatusDockIndicators({ readiness: system, gpu, providers, apiOnline });

  return <main className="app-shell">
    {/* PR012 — ETAPA 3: the cinematic Sidebar Premium. Same navigation
        surface as before (embedded views via setActive, full routes via
        router.push) — only the visual organization and the badge
        allow-list change. */}
    <Sidebar
      groups={sidebarGroups}
      activeId={active}
      onNavigate={handleSidebarNavigate}
      collapsed={!sidebar}
      brand={{ name: 'BROBOND', sub: API_URL ? 'Remote API' : 'Local instance' }}
      onBrandClick={() => setActive('dashboard')}
      footer={
        <>
          <div className="gpu-card">
            <div className="gpu-head"><span><span className={`status-dot ${gpu?.available ? '' : 'off'}`} /> {gpu === null ? 'Checking…' : gpu.available ? 'GPU ready' : 'No GPU'}</span><MoreHorizontal size={16} /></div>
            <strong>{gpu === null ? 'Reading system' : gpu.available ? 'CUDA device' : (gpu.backend || 'cpu').toUpperCase()}</strong>
            <div className="gpu-meter"><i style={{ width: gpu?.available ? '100%' : '0%' }} /></div>
            <small>{gpu === null ? 'querying /api/v1/system/gpu' : (gpu.message ?? (gpu.available ? 'inference capable' : 'inference disabled'))}</small>
          </div>
          <button className="settings" onClick={() => setActive('assets')}><Settings2 size={17} /><span>Settings</span></button>
          <button className="profile" onClick={() => setAuthOpen(true)}><div className="avatar">{user ? user.name.slice(0, 2).toUpperCase() : '—'}</div><span><strong>{user?.name ?? 'Not signed in'}</strong><small>{user ? user.email : 'Sign in to sync'}</small></span><MoreHorizontal size={16} /></button>
        </>
      }
    />

    <section className="main-area">
      <header className="topbar"><button className="icon-button mobile-menu" onClick={() => setSidebar(!sidebar)}><Menu size={19} /></button><div className="crumb"><span>Workspace</span><span>/</span><strong>{moduleTitle}</strong></div><div className="top-actions"><div className="search"><Search size={16} /><input placeholder="Search projects..." /></div><button className="icon-button"><CircleHelp size={18} /></button><button className="icon-button notification"><Bell size={18} /><i /></button><button className="new-button" onClick={create}><Plus size={17} /> New creation</button></div></header>
      <div className="content">
        {active === 'director' && <DirectorStudio activePersona={activePersona} style={style} selectedLora={selectedLora} loras={loras} onRenderImage={text => { setPrompt(text); setActive('image'); setGenerated(false); }} />}
        {active === 'dashboard' && <Dashboard onNavigate={setActive} onCreate={create} user={user} greeting={greeting} assetCount={assetCount} system={system} />}
        {active === 'image' && <ImageStudio prompt={prompt} setPrompt={setPrompt} generated={generated} setGenerated={setGenerated} personas={personas} activePersona={activePersona} onSelectPersona={selectPersona} style={style} setStyle={setStyle} loras={loras} selectedLora={selectedLora} setSelectedLora={setSelectedLora} selectedWardrobe={selectedWardrobe} onToggleWardrobe={toggleWardrobe} aspectRatio={aspectRatio} setAspectRatio={setAspectRatio} duration={duration} setDuration={setDuration} cameraPreset={cameraPreset} setCameraPreset={setCameraPreset} />}
        {active === 'video' && <VideoStudio personas={personas} activePersona={activePersona} onSelectPersona={selectPersona} style={style} setStyle={setStyle} loras={loras} selectedLora={selectedLora} setSelectedLora={setSelectedLora} selectedWardrobe={selectedWardrobe} onToggleWardrobe={toggleWardrobe} aspectRatio={aspectRatio} setAspectRatio={setAspectRatio} duration={duration} setDuration={setDuration} cameraPreset={cameraPreset} setCameraPreset={setCameraPreset} />}
        {active === 'persona' && <PersonaStudio />}
        {active === 'storyboard' && <Storyboard />}
        {active === 'assets' && <Assets onCounted={setAssetCount} />}
      </div>
      {/* PR012 — ETAPA 6: Status Dock. Replaces the old sidebar "Readiness"
          list with a single bottom bar (never taller than 52px). */}
      <StatusDock indicators={statusDockIndicators} />
    </section>
    {authOpen && <LoginScreen user={user} online={apiOnline} onAuthenticated={setUser} onClose={() => setAuthOpen(false)} />}
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
type DirectorStudioProps = {
  onRenderImage: (prompt: string) => void;
  activePersona: PersonaProfile | null;
  style: string;
  selectedLora: string;
  loras: LoraVersion[];
};

function DirectorStudio({ onRenderImage, activePersona, style, selectedLora, loras }: DirectorStudioProps) {
  const [intent, setIntent] = useState('');
  // 0 means "auto" — the director clamps to 4–8 scenes, exactly like the
  // previous chip row (`null` scene_count). HeroWorkspace's numeric field
  // (ETAPA 4) needs a plain number, so 0 is the sentinel translated back to
  // `null` right before the (unchanged) `directIntent` call below.
  const [sceneCount, setSceneCount] = useState(0);
  const [language, setLanguage] = useState('pt-BR');
  const [platform, setPlatform] = useState('instagram');
  const [brief, setBrief] = useState<DirectorBrief | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [status, setStatus] = useState<number | undefined>();
  const [errorType, setErrorType] = useState<NetworkErrorType | undefined>();

  const direct = async () => {
    if (!intent.trim()) return;
    setLoading(true); setError(undefined); setErrorType(undefined);
    const result = await directIntent({ intent: intent.trim(), scene_count: sceneCount || null });
    if (result.remote) setBrief(result.data); else setBrief(null);
    setError(result.error); setStatus(result.status); setErrorType(result.errorType);
    setLoading(false);
  };

  const examples = [
    'Quero vender uma camiseta artesanal',
    'Um reels vertical para a loja',
    'Documentário sobre artesãos locais',
    'A product commercial for shoes',
  ];

  // PR012 — ETAPA 4: the Live Storyboard Preview reads straight off the
  // same `DirectorBrief.beats` this file already gets from `directIntent`
  // (untouched contract) — one preview "scene" per beat, exactly the
  // cinematic-placeholder behaviour the spec asks for before anything
  // renders.
  const scenePreviews: HeroWorkspaceScenePreview[] = (brief?.beats ?? []).map(beat => ({
    id: `beat-${beat.number}`,
    sceneNumber: beat.number,
    title: beat.objective,
    mood: beat.emotion,
  }));

  const loraName = loras.find(item => item.asset_id === selectedLora)?.name ?? null;

  return <>
    <PageHeader eyebrow="BROBOND CORE · DIRECTOR" title="Say what you want to exist" description="Describe the intention in plain language. The director answers with concept, script, scenes, cameras, music and duration — you never write a technical prompt.">
      <button className="primary-button" onClick={direct} disabled={loading || !intent.trim()}>{loading ? 'Directing…' : <><Sparkles size={16} /> Direct it</>}</button>
    </PageHeader>

    {/* PR012 — ETAPA 5: the Identity Bar, always visible above the
        workspace, showing exactly what this generation will use. */}
    <IdentityBar
      avatarUrl={(activePersona ? mainImage(activePersona)?.url : null) ?? null}
      personaName={activePersona?.name ?? null}
      style={style || activePersona?.default_style || null}
      lora={loraName}
      status="ready"
    />

    <div className="example-row">
      {examples.map(example => <button key={example} className="example-chip" onClick={() => setIntent(example)}>{example}</button>)}
    </div>

    {/* PR012 — ETAPA 4: the Hero Workspace — Creative Brief (left) and
        Live Storyboard Preview (right), replacing the previous
        control-panel / brief-canvas pair. `direct()` is the exact same
        `directIntent()` call as before. */}
    <HeroWorkspace
      brief={intent}
      onBriefChange={setIntent}
      sceneCount={sceneCount}
      onSceneCountChange={setSceneCount}
      language={language}
      onLanguageChange={setLanguage}
      platform={platform}
      onPlatformChange={setPlatform}
      onSubmit={direct}
      submitting={loading}
      scenes={scenePreviews}
    />

    <Notice error={error} status={status} errorType={errorType} />
    {isUnreachable({ errorType }) && !brief && <p className="muted">The API did not answer — nothing is being faked here.</p>}

    {brief && <div className="brief-canvas">
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
    </div>}
  </>;
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

type StudioPersonaProps = {
  personas: PersonaProfile[];
  activePersona: PersonaProfile | null;
  onSelectPersona: (persona: PersonaProfile | null) => void;
  style: string;
  setStyle: (style: string) => void;
  loras: LoraVersion[];
  selectedLora: string;
  setSelectedLora: (value: string) => void;
  selectedWardrobe: string[];
  onToggleWardrobe: (name: string) => void;
};

/**
 * PR004 (ETAPA 4) — the Identity panel shared by the Image and Video
 * studios: the PersonaSelector (dropdown + search), the style field with
 * the "Usar estilo da Persona" shortcut, and the live PersonaPreview.
 * The persona flows Persona → Prompt → Compile → GenerationSpec → Provider;
 * everything below this panel stays exactly as it was.
 */
function IdentityPanel({ personas, activePersona, onSelectPersona, style, setStyle, loras, selectedWardrobe, onToggleWardrobe }: StudioPersonaProps) {
  return <div className="identity-panel">
    <div className="panel-heading"><span>Identity</span><span className="muted">{activePersona ? `v${activePersona.revision}` : 'none'}</span></div>
    <PersonaSelector personas={personas} selectedId={activePersona?.id ?? null} onSelect={onSelectPersona} />
    <label>Style{activePersona?.default_style ? <span>persona default</span> : <span>optional</span>}
      <input value={style} onChange={event => setStyle(event.target.value)} placeholder={activePersona?.default_style || 'e.g. cinematic realism'} />
    </label>
    {activePersona?.default_style && <button type="button" className="secondary-button full style-button" onClick={() => setStyle(activePersona.default_style)}><WandSparkles size={14} /> Usar estilo da Persona</button>}
    <PersonaPreview persona={activePersona} loras={loras} selectedWardrobe={selectedWardrobe} onToggleWardrobe={onToggleWardrobe} />
  </div>;
}

/**
 * PR004.1 — the project-level creative controls, owned by Home so the
 * Project Memory contract (ProjectMemoryState) can persist and restore
 * them. The studios render exactly the same controls as before; only the
 * state owner moved.
 */
type StudioCreativeProps = {
  aspectRatio: string;
  setAspectRatio: (value: string) => void;
  duration: number;
  setDuration: (value: number) => void;
  cameraPreset: string;
  setCameraPreset: (value: string) => void;
};

function ImageStudio({ prompt, setPrompt, generated, setGenerated, ...creative }: { prompt: string; setPrompt: (s: string) => void; generated: boolean; setGenerated: (b: boolean) => void } & StudioPersonaProps & StudioCreativeProps) {
  const { personas, activePersona, onSelectPersona, style, setStyle, loras, selectedLora, setSelectedLora, selectedWardrobe, onToggleWardrobe, aspectRatio, setAspectRatio } = creative;
  const [loading, setLoading] = useState(false);
  const [connection, setConnection] = useState('Local preview');
  const [job, setJob] = useState<Job | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | undefined>();
  const [status, setStatus] = useState<number | undefined>();
  const [errorType, setErrorType] = useState<NetworkErrorType | undefined>();
  const [models, setModels] = useState<ModelOption[]>([]);
  const [model, setModel] = useState('flux-dev');
  const [resolution, setResolution] = useState('1024');
  const [controlnet, setControlnet] = useState('none');
  const [controlScale, setControlScale] = useState(0.8);
  const [ipScale, setIpScale] = useState(0.7);
  const [referenceAssetId, setReferenceAssetId] = useState('');
  const [referenceStatus, setReferenceStatus] = useState('');
  const [enhancing, setEnhancing] = useState(false);

  useEffect(() => {
    imageModels().then(result => { if (result.remote && result.data.length) setModels(result.data); });
    // PR004: the persona's LoRA versions arrive as a prop (Home owns them so
    // the Project Memory can restore the last choice); the legacy
    // `brobond_persona_id` localStorage lookup is superseded.
  }, []);

  const handleReference = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]; if (!file) return;
    setReferenceStatus('Uploading reference...'); const result = await uploadAsset(file);
    if (result.remote) { setReferenceAssetId(result.data.id); setReferenceStatus('Reference ready'); }
    else setReferenceStatus(failureMessage(result, 'API offline — the reference was not uploaded.'));
    event.target.value = '';
  };

  const enhance = async () => {
    setEnhancing(true); setError(undefined); setErrorType(undefined);
    const result = await enhancePrompt({ prompt, style: 'cinematic realism', camera: 'medium shot, 85mm lens' });
    if (result.remote) setPrompt(result.data.enhanced);
    setError(result.error); setStatus(result.status); setErrorType(result.errorType);
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
      // PR004 (ETAPAS 3/4): the persona pipeline. The compiler resolves the
      // identity, the default style, the LoRA, the wardrobe and the
      // reference image automatically; the explicit controls above still win.
      persona_id: activePersona?.id || undefined,
      style: style || undefined,
      wardrobe: selectedWardrobe.length ? selectedWardrobe : undefined,
    });
    if (result.remote) {
      setJob(result.data); setProgress(result.data.progress);
      // PR002: job tracking is authenticated. A job created without a token
      // exists, but its stream is tenant-scoped — say so instead of implying
      // it will update.
      const signedIn = getAuthToken() !== null;
      setConnection(signedIn ? `Job ${result.data.id.slice(0, 8)} queued` : 'Job created — sign in to track it');
    }
    else { setJob(null); setConnection(isUnreachable(result) ? 'API unreachable' : 'Request rejected'); }
    setError(result.error); setStatus(result.status); setErrorType(result.errorType);
    setLoading(false);
  };

  return <StudioLayout type="Image" onGenerate={generate}><div className="studio-grid"><div className="control-panel"><IdentityPanel {...creative} /><div className="panel-heading"><span>Prompt</span><button className="magic-button" onClick={enhance}><WandSparkles size={14} /> {enhancing ? 'Enhancing...' : 'Enhance'}</button></div><textarea value={prompt} onChange={e => setPrompt(e.target.value)} /><div className="prompt-meta"><span>{prompt.length} / 2,000</span><button onClick={() => setPrompt('')}>Reset</button></div><div className="form-row"><label>Model<select value={model} onChange={event => setModel(event.target.value)}>{(models.length ? models : [{ id: model, label: model, status: 'unknown' }]).map(option => <option key={option.id} value={option.id}>{option.label ?? option.id}{option.status ? ` · ${option.status}` : ''}</option>)}</select></label><label>Aspect ratio<select value={aspectRatio} onChange={event => setAspectRatio(event.target.value)}><option value="16:9">16:9 · Landscape</option><option value="1:1">1:1 · Square</option><option value="9:16">9:16 · Portrait</option></select></label></div><div className="form-row"><label>Resolution<select value={resolution} onChange={event => setResolution(event.target.value)}><option value="1024">1024 · HD</option><option value="2048">2048 · 2K</option></select></label><label>Seed<div className="input-with-action"><input value="Random" readOnly /><button><Aperture size={14} /></button></div></label></div><div className="conditioning-box"><div className="panel-heading"><span>Structure &amp; identity</span><span className="muted">Optional</span></div><label>ControlNet<select value={controlnet} onChange={event => setControlnet(event.target.value)}><option value="none">None</option><option value="pose">OpenPose</option><option value="depth">Depth map</option><option value="canny">Canny edges</option><option value="tile">Tile detail</option></select></label><div className="mini-slider"><span>Control strength <b>{controlScale.toFixed(1)}</b></span><input type="range" min="0" max="2" step="0.1" value={controlScale} onChange={event => setControlScale(Number(event.target.value))} /></div><div className="mini-slider"><span>IP Adapter <b>{ipScale.toFixed(1)}</b></span><input type="range" min="0" max="1" step="0.1" value={ipScale} onChange={event => setIpScale(Number(event.target.value))} /></div></div><div className="panel-footer"><label className="secondary-button lora-select"><Plus size={15} /> {loras.length ? <select value={selectedLora} onChange={event => setSelectedLora(event.target.value)}><option value="">Add LoRA</option>{loras.map(lora => <option value={lora.asset_id} key={lora.asset_id}>{lora.version}</option>)}</select> : 'Add LoRA'}</label><label className="secondary-button upload-label"><ImageIcon size={15} /> {referenceStatus || 'Reference image'}<input type="file" accept="image/*" onChange={handleReference} /></label></div><Notice error={error} status={status} errorType={errorType} /></div><div className={`generation-canvas ${generated ? 'has-result' : ''}`}>{generated ? <><div className="result-art">{job?.output_url ? <img className="result-image" src={job.output_url} alt={prompt} /> : <div className="result-pending"><Box size={26} /><span>{job?.status === 'failed' ? 'The render failed — no image was produced' : job?.status === 'cancelled' ? 'Cancelled — nothing was produced' : loading || job ? 'Rendering…' : 'No image yet'}</span></div>}{job?.output_url && <span className="result-label">{model} · {aspectRatio}</span>}</div><div className="result-toolbar"><span>{loading ? 'Submitting generation...' : `${connection}${job?.output_url ? ' · ready' : ''}`}{(loading || (job && job.status === 'running')) && <i className="job-progress"><b style={{ width: `${progress}%` }} /></i>}</span><div>{job && (job.status === 'queued' || job.status === 'running') && <button className="cancel-job" onClick={async () => { await cancelJob(job.id); setConnection('Job cancelled'); setLoading(false); }}>Cancel</button>}{job?.output_url && <a className="icon-button" href={job.output_url} target="_blank" rel="noreferrer"><Download size={16} /></a>}</div></div></> : <div className="empty-canvas"><div className="empty-icon"><Sparkles size={23} /></div><h3>Your canvas is empty</h3><p>Describe an image and hit Generate<br />to bring your idea to life.</p><span>The result shown here is always the real render</span></div>}</div></div></StudioLayout>; }

function VideoStudio(props: StudioPersonaProps & StudioCreativeProps) {
  // PR004.1: duration/aspect/camera are project-level controls owned by Home
  // (Project Memory); aliased so the rendered markup is byte-identical.
  const { personas, activePersona, onSelectPersona, style, setStyle, loras, selectedLora, setSelectedLora, selectedWardrobe, onToggleWardrobe, aspectRatio: aspect, setAspectRatio: setAspect, duration, setDuration, cameraPreset: cameraMotion, setCameraPreset: setCameraMotion } = props;
  const [connection, setConnection] = useState('Ready to render');
  const [job, setJob] = useState<Job | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | undefined>();
  const [status, setStatus] = useState<number | undefined>();
  const [errorType, setErrorType] = useState<NetworkErrorType | undefined>();
  const [brief, setBrief] = useState('A cinematic slow dolly-in through a futuristic city at night, neon reflections on wet pavement');
  const [models, setModels] = useState<ModelOption[]>([]);
  const [model, setModel] = useState('wan-2.1-t2v');
  const [nativeAudio, setNativeAudio] = useState(true);
  const [cinematicMode, setCinematicMode] = useState(true);

  useEffect(() => {
    videoModels().then(result => { if (result.remote && result.data.length) setModels(result.data); });
    // PR004: the persona's LoRA versions arrive as a prop (same rule as the
    // Image Studio); the legacy `brobond_persona_id` lookup is superseded.
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
    const result = await createVideoJob({
      prompt: brief, model, mode: 'text-to-video', duration_seconds: duration, fps: 24, aspect_ratio: aspect,
      cinematic_mode: cinematicMode, native_audio: nativeAudio, lora_id: selectedLora || undefined,
      // PR004 (ETAPAS 3/5): duration, camera, persona and style — the
      // compiler resolves the identity, LoRA, wardrobe and reference.
      camera_motion: cameraMotion,
      persona_id: activePersona?.id || undefined,
      style: style || undefined,
      wardrobe: selectedWardrobe.length ? selectedWardrobe : undefined,
    });
    if (result.remote) {
      setJob(result.data); setProgress(result.data.progress);
      // PR002: job tracking is authenticated; a tokenless job is not trackable.
      const signedIn = getAuthToken() !== null;
      setConnection(signedIn ? `Job ${result.data.id.slice(0, 8)} queued` : 'Job created — sign in to track it');
    }
    else { setJob(null); setConnection(isUnreachable(result) ? 'API unreachable' : 'Request rejected'); }
    setError(result.error); setStatus(result.status); setErrorType(result.errorType);
  };

  return <StudioLayout type="Video" onGenerate={generate}><div className="video-layout"><div className="control-panel"><IdentityPanel {...props} /><div className="tab-row"><button className="active">Text to video</button><button>Image to video</button></div><div className="panel-heading"><span>Describe your shot</span></div><textarea value={brief} onChange={event => setBrief(event.target.value)} /><label>Model<select value={model} onChange={event => setModel(event.target.value)}>{(models.length ? models : [{ id: model, label: model, status: 'unknown' }]).map(option => <option key={option.id} value={option.id}>{option.label ?? option.id}{option.status ? ` · ${option.status}` : ''}</option>)}</select></label><label>Duration <div className="chip-row">{[5, 10, 15].map(value => <Chip key={value} active={duration === value} onClick={() => setDuration(value)}>{value}s</Chip>)}</div></label><label>Format <div className="chip-row">{['16:9', '9:16', '1:1'].map(value => <Chip key={value} active={aspect === value} onClick={() => setAspect(value)}>{value}</Chip>)}</div></label><label>Camera <div className="chip-row">{['static', 'pan', 'tilt', 'zoom', 'tracking', 'crane'].map(value => <Chip key={value} active={cameraMotion === value} onClick={() => setCameraMotion(value)}>{value}</Chip>)}</div></label>{loras.length > 0 && <label>Persona LoRA<select value={selectedLora} onChange={event => setSelectedLora(event.target.value)}><option value="">None</option>{loras.map(lora => <option value={lora.asset_id} key={lora.asset_id}>{lora.version}</option>)}</select></label>}<div className="setting-line"><span>Native audio</span><button onClick={() => setNativeAudio(!nativeAudio)}><Toggle on={nativeAudio} /></button></div><div className="setting-line"><span>Cinematic mode</span><button onClick={() => setCinematicMode(!cinematicMode)}><Toggle on={cinematicMode} /></button></div><Notice error={error} status={status} errorType={errorType} /></div><div className="video-canvas"><div className="video-placeholder">{job?.output_url ? <video className="result-image" src={job.output_url} controls /> : <><div className="video-lines" /><Play size={28} fill="currentColor" /><span>{job?.status === 'failed' ? 'The render failed — no video was produced' : connection}</span></>}{job && (job.status === 'queued' || job.status === 'running') && <><div className="render-progress"><i style={{ width: `${progress}%` }} /></div><button className="cancel-job" onClick={async () => { await cancelJob(job.id); setConnection('Render cancelled'); }}>Cancel render</button></>}</div><div className="timeline"><span>00:00</span><div className="timeline-track"><i style={{ width: `${Math.max(progress, 2)}%` }} /></div><span>{`00:0${duration}`.slice(0, 5)}</span></div></div></div></StudioLayout>; }

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
    if (!created.remote) { setError(created.error); setStatus(isUnreachable(created) ? 'API unreachable · start FastAPI to train' : 'Persona rejected'); return; }
    const id = String(created.data.id); setPersonaId(id);
    // LEGACY (pre-PR004): the Persona Lab still writes the legacy persona id
    // (Project Memory supersedes it); the write goes through the adapter's
    // named accessor — no component names the raw key (PR004.1).
    setLegacyPersonaId(id); setStatus('Queuing LoRA training...');
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

// PR013 — V4.0.1: the whole assets experience (upload engine done there,
// responsive grid, preview, filters, search, empty states) now lives in
// app/components/studio/assets. This wrapper only owns the page chrome and
// the counted description — the numbers stay real or they stay unknown.
function Assets({ onCounted }: { onCounted: (count: number) => void }) {
  const [counts, setCounts] = useState<LibraryCounts | null>(null);
  const enqueue = useRef<(files: File[]) => void>(() => undefined);
  const description = counts
    ? `${counts.all} assets — ${counts.image} images · ${counts.video} videos. Drop files anywhere on this page.`
    : 'Everything you make, in one calm place. Counts are read from the API.';
  return <><PageHeader eyebrow="LIBRARY" title="Your creative archive" description={description}><AssetBrowseButton label="Upload assets" onFiles={files => enqueue.current(files)} /></PageHeader><AssetLibraryClient onCounted={(next) => { setCounts(next); onCounted(next.all); }} registerEnqueue={(handler) => { enqueue.current = handler; }} /></>;
}
