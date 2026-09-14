'use client';

import { useEffect, useState } from 'react';
import { Asset, AuthUser, authenticate, createImageJob, createPersona, createVideoJob, expandStoryboard, listAssets, uploadAsset } from '../lib/api';
import {
  Aperture, ArrowUpRight, AudioLines, Bell, Box, ChevronDown, CircleHelp, Clapperboard,
  Clock3, Download, Folder, Gauge, Grid2X2, Image as ImageIcon, Layers3, Library,
  Menu, MessageSquareText, MoreHorizontal, Move3d, Play, Plus, Search, Settings2,
  Sparkles, Square, UserRound, WandSparkles, X, Zap, LogIn, LockKeyhole,
} from 'lucide-react';

const modules = [
  { id: 'dashboard', label: 'Overview', icon: Grid2X2 },
  { id: 'image', label: 'Image generation', icon: ImageIcon },
  { id: 'video', label: 'Video generation', icon: Clapperboard },
  { id: 'motion', label: 'Motion control', icon: Move3d },
  { id: 'persona', label: 'Personas', icon: UserRound },
  { id: 'storyboard', label: 'Storyboard', icon: Layers3 },
  { id: 'assets', label: 'Assets', icon: Library },
];

const projects = [
  { title: 'Neon Tokyo / Film 01', type: 'Video', date: 'Edited 2m ago', tone: 'purple', icon: Clapperboard },
  { title: 'BROBOND Identity Study', type: 'Image', date: 'Edited yesterday', tone: 'orange', icon: ImageIcon },
  { title: 'The Last Horizon', type: 'Storyboard', date: 'Edited 3 days ago', tone: 'blue', icon: Layers3 },
];

function Toggle({ on = true }: { on?: boolean }) { return <span className={`toggle ${on ? 'on' : ''}`}><i /></span>; }
function Chip({ children, active = false }: { children: React.ReactNode; active?: boolean }) { return <button className={`chip ${active ? 'active' : ''}`}>{children}</button>; }

export default function Home() {
  const [active, setActive] = useState('dashboard');
  const [prompt, setPrompt] = useState('A cinematic portrait of a Brazilian athlete in a brutalist city at blue hour');
  const [generated, setGenerated] = useState(false);
  const [sidebar, setSidebar] = useState(true);
  const [authOpen, setAuthOpen] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);

  const moduleTitle = modules.find(m => m.id === active)?.label ?? 'Overview';
  const create = () => { setActive('image'); setGenerated(false); };

  return <main className="app-shell">
    <aside className={`sidebar ${sidebar ? '' : 'collapsed'}`}>
      <div className="brand"><div className="brand-mark"><Aperture size={19} /></div><span>BROBOND</span><small>AI STUDIO</small></div>
      <div className="workspace-select"><div className="workspace-avatar">B</div><div><strong>Personal workspace</strong><span>Local instance</span></div><ChevronDown size={14} /></div>
      <div className="nav-label">WORKSPACE</div>
      <nav>{modules.map(item => { const Icon = item.icon; return <button key={item.id} className={active === item.id ? 'selected' : ''} onClick={() => setActive(item.id)}><Icon size={18} /><span>{item.label}</span>{item.id === 'video' && <b className="nav-badge">BETA</b>}</button>; })}</nav>
      <div className="nav-label library-label">LIBRARY</div>
      <nav><button onClick={() => setActive('assets')}><Folder size={18} /><span>Projects</span></button><button onClick={() => setActive('assets')}><Library size={18} /><span>All assets</span></button></nav>
      <div className="sidebar-bottom"><div className="gpu-card"><div className="gpu-head"><span><span className="status-dot" /> GPU ready</span><MoreHorizontal size={16} /></div><strong>RTX 4090</strong><div className="gpu-meter"><i /></div><small>18.4 / 24 GB VRAM</small></div><button className="settings" onClick={() => setActive('assets')}><Settings2 size={17} /><span>Settings</span></button><button className="profile" onClick={() => setAuthOpen(true)}><div className="avatar">{user ? user.name.slice(0, 2).toUpperCase() : 'PM'}</div><span><strong>{user?.name ?? 'Petrick Martins'}</strong><small>{user ? user.email : 'Sign in to sync'}</small></span><MoreHorizontal size={16} /></button></div>
    </aside>

    <section className="main-area">
      <header className="topbar"><button className="icon-button mobile-menu" onClick={() => setSidebar(!sidebar)}><Menu size={19} /></button><div className="crumb"><span>Workspace</span><span>/</span><strong>{moduleTitle}</strong></div><div className="top-actions"><div className="search"><Search size={16} /><input placeholder="Search projects..." /></div><button className="icon-button"><CircleHelp size={18} /></button><button className="icon-button notification"><Bell size={18} /><i /></button><button className="new-button" onClick={create}><Plus size={17} /> New creation</button></div></header>
      <div className="content">
        {active === 'dashboard' && <Dashboard onNavigate={setActive} onCreate={create} />}
        {active === 'image' && <ImageStudio prompt={prompt} setPrompt={setPrompt} generated={generated} setGenerated={setGenerated} />}
        {active === 'video' && <VideoStudio />}
        {active === 'motion' && <MotionStudio />}
        {active === 'persona' && <PersonaStudio />}
        {active === 'storyboard' && <Storyboard />}
        {active === 'assets' && <Assets />}
      </div>
    </section>
    {authOpen && <AuthModal user={user} onAuthenticated={setUser} onClose={() => setAuthOpen(false)} />}
  </main>;
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
    if (mode === 'login') { onAuthenticated({ id: 'local', email: email || 'local@brobond.ai', name: name || 'Petrick Martins' }); onClose(); }
    else setMessage('API offline. Start FastAPI to create a persistent account.');
  };
  const logout = () => { localStorage.removeItem('brobond_access_token'); onAuthenticated(null); onClose(); };
  return <div className="modal-backdrop" onClick={onClose}><div className="auth-modal" onClick={event => event.stopPropagation()}><button className="modal-close" onClick={onClose}><X size={17} /></button>{user ? <><div className="auth-icon"><LockKeyhole size={20} /></div><h2>{user.name}</h2><p className="auth-subtitle">{user.email}</p><button className="secondary-button full" onClick={logout}>Sign out</button></> : <><div className="auth-icon"><LogIn size={20} /></div><div className="auth-switch"><button className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')}>Sign in</button><button className={mode === 'register' ? 'active' : ''} onClick={() => setMode('register')}>Create account</button></div><h2>{mode === 'login' ? 'Welcome back' : 'Create your workspace'}</h2><p className="auth-subtitle">{mode === 'login' ? 'Sign in to sync your creations and assets.' : 'Start building your private visual studio.'}</p><form onSubmit={submit}>{mode === 'register' && <input value={name} onChange={event => setName(event.target.value)} placeholder="Full name" required />}<input type="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="Email address" required /><input type="password" value={password} onChange={event => setPassword(event.target.value)} placeholder="Password · 8+ characters" minLength={8} required /><button className="primary-button full" type="submit">{mode === 'login' ? 'Sign in' : 'Create account'} <ArrowUpRight size={15} /></button></form>{message && <small className="auth-message">{message}</small>}</>}</div></div>;
}

function PageHeader({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children?: React.ReactNode }) { return <div className="page-header"><div><div className="eyebrow"><Sparkles size={13} /> {eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{children}</div>; }

function Dashboard({ onNavigate, onCreate }: { onNavigate: (id: string) => void; onCreate: () => void }) {
  const cards = [{ id: 'image', title: 'Image generation', desc: 'Create ultra-realistic images', icon: ImageIcon, color: 'purple', stat: '12 renders' }, { id: 'video', title: 'Video generation', desc: 'Bring your ideas to life', icon: Clapperboard, color: 'orange', stat: '4 renders' }, { id: 'motion', title: 'Motion control', desc: 'Direct every camera move', icon: Move3d, color: 'cyan', stat: 'New' }, { id: 'persona', title: 'Persona', desc: 'Build consistent characters', icon: UserRound, color: 'pink', stat: '2 personas' }];
  return <><PageHeader eyebrow="PERSONAL WORKSPACE" title="Good evening, Petrick" description="What will you create today?"><button className="primary-button" onClick={onCreate}><Plus size={18} /> Start creating</button></PageHeader><section className="hero-banner"><div className="hero-copy"><span className="pill"><Zap size={13} /> NEW WORKFLOW</span><h2>From a thought<br />to a <em>masterpiece.</em></h2><p>Generate, direct and refine your visual stories in one focused workspace.</p><button className="light-button" onClick={onCreate}>Explore image generation <ArrowUpRight size={15} /></button></div><div className="hero-art"><div className="orb orb-one" /><div className="orb orb-two" /><div className="hero-grid" /><span className="art-caption">BROBOND / 001</span></div></section><div className="section-row"><div><h2 className="section-title">Creative tools</h2><p className="section-subtitle">Everything you need to make your next idea real.</p></div><button className="text-button">View all <ArrowUpRight size={14} /></button></div><div className="tool-grid">{cards.map(card => { const Icon = card.icon; return <button className="tool-card" key={card.id} onClick={() => onNavigate(card.id)}><div className={`tool-icon ${card.color}`}><Icon size={20} /></div><div className="card-arrow"><ArrowUpRight size={16} /></div><h3>{card.title}</h3><p>{card.desc}</p><span className="tool-stat">{card.stat}</span></button>; })}</div><div className="section-row recent-row"><div><h2 className="section-title">Recent projects</h2><p className="section-subtitle">Pick up where you left off.</p></div><button className="text-button" onClick={() => onNavigate('assets')}>View library <ArrowUpRight size={14} /></button></div><div className="project-grid">{projects.map(project => { const Icon = project.icon; return <div className="project-card" key={project.title}><div className={`project-thumb ${project.tone}`}><Icon size={31} /><span className="play-overlay"><Play size={13} fill="currentColor" /></span></div><div className="project-info"><div><h3>{project.title}</h3><p>{project.type} · {project.date}</p></div><button className="icon-button"><MoreHorizontal size={17} /></button></div></div>; })}</div></>;
}

function StudioLayout({ type, children, onGenerate }: { type: string; children: React.ReactNode; onGenerate?: () => void }) { return <><PageHeader eyebrow={`${type.toUpperCase()} WORKSPACE`} title={type === 'Image' ? 'Image generation' : `${type} studio`} description={type === 'Image' ? 'Turn your imagination into high-fidelity visuals.' : 'Compose and direct your next visual sequence.'}><div className="header-actions"><button className="icon-button"><Clock3 size={17} /></button><button className="primary-button" onClick={onGenerate}><Sparkles size={16} /> Generate</button></div></PageHeader>{children}</>; }

function ImageStudio({ prompt, setPrompt, generated, setGenerated }: { prompt: string; setPrompt: (s: string) => void; generated: boolean; setGenerated: (b: boolean) => void }) {
  const [loading, setLoading] = useState(false);
  const [connection, setConnection] = useState('Local preview');
  const generate = async () => {
    setLoading(true);
    const result = await createImageJob({ prompt, model: 'flux-1.1-pro-ultra', aspect_ratio: '16:9', resolution: '2048', guidance_scale: 7.5, steps: 28 });
    setConnection(result.remote ? `Job ${result.data.id.slice(0, 8)} queued` : 'Local preview');
    setGenerated(true);
    setLoading(false);
  };
  return <StudioLayout type="Image" onGenerate={generate}><div className="studio-grid"><div className="control-panel"><div className="panel-heading"><span>Prompt</span><button className="magic-button"><WandSparkles size={14} /> Enhance</button></div><textarea value={prompt} onChange={e => setPrompt(e.target.value)} /><div className="prompt-meta"><span>72 / 2,000</span><button>Reset</button></div><label>Negative prompt <span>Optional</span></label><input placeholder="Things to avoid in your image..." /><div className="form-row"><label>Model<select><option>Flux 1.1 Pro Ultra</option><option>Flux Dev</option></select></label><label>Aspect ratio<select><option>16:9 · Landscape</option><option>1:1 · Square</option><option>9:16 · Portrait</option></select></label></div><div className="form-row"><label>Resolution<select><option>2048 × 1152 · 2K</option><option>1024 × 576 · HD</option><option>4096 × 2304 · 4K</option></select></label><label>Seed<div className="input-with-action"><input value="Random" readOnly /><button><Aperture size={14} /></button></div></label></div><div className="slider-row"><span>Guidance scale <b>7.5</b></span><input type="range" defaultValue="54" /></div><div className="slider-row"><span>Steps <b>28</b></span><input type="range" defaultValue="43" /></div><div className="panel-footer"><button className="secondary-button"><Plus size={15} /> Add LoRA</button><button className="secondary-button"><ImageIcon size={15} /> Reference</button></div></div><div className={`generation-canvas ${generated ? 'has-result' : ''}`}>{generated ? <><div className="result-art"><div className="result-light" /><div className="result-person"><div className="head" /><div className="body" /></div><span className="result-label">FLUX / 2K</span></div><div className="result-toolbar"><span>{loading ? 'Submitting generation...' : `${connection} · ready`}</span><div><button className="icon-button"><Download size={16} /></button><button className="icon-button"><MoreHorizontal size={16} /></button></div></div></> : <div className="empty-canvas"><div className="empty-icon"><Sparkles size={23} /></div><h3>Your canvas is empty</h3><p>Describe an image and hit Generate<br />to bring your idea to life.</p><span>⌘ Enter to generate</span></div>}</div></div></StudioLayout>; }

function VideoStudio() {
  const [connection, setConnection] = useState('Ready to render');
  const generate = async () => {
    setConnection('Submitting video job...');
    const result = await createVideoJob({ prompt: 'A cinematic slow dolly-in through a futuristic city at night, neon reflections on wet pavement', mode: 'text-to-video', duration_seconds: 5, fps: 24, aspect_ratio: '16:9', camera_motion: 'dolly-in', cinematic_mode: true, native_audio: true });
    setConnection(result.remote ? `Job ${result.data.id.slice(0, 8)} queued` : 'Local preview · ready');
  };
  return <StudioLayout type="Video" onGenerate={generate}><div className="video-layout"><div className="control-panel"><div className="tab-row"><button className="active">Text to video</button><button>Image to video</button></div><div className="panel-heading"><span>Describe your shot</span><button className="magic-button"><WandSparkles size={14} /> Enhance</button></div><textarea placeholder="A slow dolly-in through a futuristic city..." defaultValue="A cinematic slow dolly-in through a futuristic city at night, neon reflections on wet pavement" /><label>Duration <div className="chip-row"><Chip active>5s</Chip><Chip>10s</Chip><Chip>15s</Chip></div></label><label>Format <div className="chip-row"><Chip active>16:9</Chip><Chip>9:16</Chip><Chip>1:1</Chip></div></label><label>Camera motion<select><option>Dolly in</option><option>Orbit left</option><option>Static</option></select></label><div className="setting-line"><span>Native audio</span><Toggle /></div><div className="setting-line"><span>Cinematic mode</span><Toggle /></div></div><div className="video-canvas"><div className="video-placeholder"><div className="video-lines" /><Play size={28} fill="currentColor" /><span>{connection}</span></div><div className="timeline"><span>00:00</span><div className="timeline-track"><i /></div><span>00:05</span></div></div></div></StudioLayout>; }

function MotionStudio() { return <><PageHeader eyebrow="MOTION CONTROL" title="Direct every move" description="Turn a reference frame into a precisely choreographed shot."><button className="primary-button"><Sparkles size={16} /> Generate motion</button></PageHeader><div className="motion-layout"><div className="upload-zone"><div className="upload-icon"><Move3d size={24} /></div><h3>Drop a reference image</h3><p>PNG, JPG up to 20 MB</p><button className="secondary-button"><Plus size={15} /> Upload image</button></div><div className="control-panel motion-controls"><div className="panel-heading"><span>Camera path</span><span className="muted">8 presets</span></div><div className="motion-grid">{['Dolly in','Dolly out','Orbit left','Orbit right','Crane up','Crane down','Handheld','Static'].map((x, i) => <button className={i === 0 ? 'motion-option selected' : 'motion-option'} key={x}><span className="motion-glyph">{i < 4 ? '↗' : i === 7 ? '·' : '↕'}</span>{x}</button>)}</div><label>Intensity <b className="right-value">72%</b><input type="range" defaultValue="72" /></label><label>Keyframes <b className="right-value">12</b><input type="range" defaultValue="35" /></label></div></div></>; }

function PersonaStudio() {
  const [status, setStatus] = useState('Ready to train');
  const train = async () => {
    setStatus('Registering persona...');
    const result = await createPersona({ name: 'Petrick Martins', age: 50, appearance: 'Athletic portrait', eye_color: 'Dark brown', beard: 'Short beard', hair: 'Long, tied back', height_m: 1.85, style: 'Cinematic realism', reference_asset_ids: [] });
    setStatus(result.remote ? 'Training job queued' : 'Local preview · ready to train');
  };
  return <><PageHeader eyebrow="PERSONA LAB" title="Make identity consistent" description="Train a private visual persona for stories that feel unmistakably yours."><button className="primary-button" onClick={train}><Plus size={17} /> New persona</button></PageHeader><div className="persona-layout"><div className="persona-card"><div className="persona-cover"><div className="persona-portrait"><UserRound size={42} /></div><span className="trained-badge"><span className="status-dot" /> Trained</span></div><div className="persona-body"><div><h2>Petrick Martins</h2><p>BROBOND · Athletic portrait</p></div><MoreHorizontal size={18} /><div className="persona-tags"><span>50 years</span><span>1.85m</span><span>Short beard</span><span>Tied hair</span></div><div className="persona-footer"><span><ImageIcon size={14} /> 42 reference images</span><span>LoRA v1.2</span></div></div></div><div className="training-panel"><div className="panel-heading"><span>Persona details</span><button className="text-button">Edit</button></div>{[['Appearance','Athletic, defined features'],['Eye color','Dark brown'],['Hair','Long, tied back'],['Style','Cinematic realism']].map(([a,b]) => <div className="detail-row" key={a}><span>{a}</span><strong>{b}</strong></div>)}<div className="lora-progress"><div><span>LoRA training</span><b>{status}</b></div><div className="progress"><i /></div></div><button className="secondary-button full"><Sparkles size={15} /> Use in a creation</button></div></div></>; }

function Storyboard() {
  const [status, setStatus] = useState('4 scenes');
  const generate = async () => {
    setStatus('Expanding brief...');
    const result = await expandStoryboard({ brief: 'A man walking through a futuristic city, searching for a light beyond the skyline.', scene_count: 4 });
    setStatus(result.remote ? '4 scenes · API generated' : '4 scenes · local preview');
  };
  return <><PageHeader eyebrow="STORYBOARD" title="Shape the whole story" description="Break an idea into a sequence of cinematic scenes before you render."><button className="primary-button" onClick={generate}><Sparkles size={16} /> Generate scenes</button></PageHeader><div className="story-input control-panel"><div className="panel-heading"><span>Story brief</span><button className="magic-button"><WandSparkles size={14} /> Expand brief</button></div><textarea defaultValue="A man walking through a futuristic city, searching for a light beyond the skyline." /><div className="story-options"><span>{status}</span><span>·</span><span>Connected narrative</span><button className="secondary-button">Regenerate</button></div></div><div className="scene-grid">{['The arrival','Through the city','A different sky','Beyond the light'].map((scene, i) => <div className="scene-card" key={scene}><div className={`scene-visual scene-${i}`}><span>SCENE {String(i + 1).padStart(2,'0')}</span><button className="play-overlay"><Play size={13} fill="currentColor" /></button></div><div className="scene-copy"><div><h3>{scene}</h3><p>{['Wide establishing shot · 5s','Tracking shot · 5s','Low angle · 5s','Final close-up · 5s'][i]}</p></div><MoreHorizontal size={17} /></div></div>)}</div></>; }

function Assets() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [remote, setRemote] = useState(false);
  const [uploading, setUploading] = useState(false);
  useEffect(() => { listAssets().then(result => { setRemote(result.remote); if (result.remote) setAssets(result.data); }); }, []);
  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    const result = await uploadAsset(file);
    if (result.remote) { setAssets(current => [result.data, ...current]); setRemote(true); }
    setUploading(false);
    event.target.value = '';
  };
  const demoAssets = ['Neon portrait','City motion','Golden hour','Persona reference','The horizon','Studio test'];
  return <><PageHeader eyebrow="LIBRARY" title="Your creative archive" description="Everything you make, in one calm place."><label className="primary-button upload-label"><Plus size={17} /> {uploading ? 'Uploading...' : 'Upload assets'}<input type="file" accept="image/*,video/*,audio/*" onChange={handleUpload} /></label></PageHeader><div className="asset-tabs"><button className="active">All assets <span>{remote ? assets.length : 128}</span></button><button>Images <span>84</span></button><button>Videos <span>24</span></button><button>Personas <span>2</span></button><button>Audio <span>18</span></button></div>{remote && assets.length === 0 ? <div className="empty-library"><Library size={22} /><h3>Your library is empty</h3><p>Upload a reference or generate your first asset.</p></div> : <div className="asset-grid">{(remote ? assets : demoAssets).map((item, i) => { const asset = typeof item === 'string' ? null : item; const title = asset?.name ?? item as string; return <div className="asset-item" key={asset?.id ?? title}><div className={`asset-image asset-${i % 6}`} style={asset ? { backgroundImage: `url(${asset.url})`, backgroundSize: 'cover', backgroundPosition: 'center' } : undefined}><span>{asset?.kind === 'video' ? <Clapperboard size={18} /> : <ImageIcon size={18} />}</span></div><div><strong>{title}</strong><small>{asset ? `${asset.kind} · synced` : i % 2 ? 'Video · 24 MB' : 'Image · 4.2 MB'}</small></div><MoreHorizontal size={16} /></div>; })}</div>}</>;
}
