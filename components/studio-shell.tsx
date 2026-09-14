"use client";

import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  AudioWaveform,
  Bell,
  Camera,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clapperboard,
  Clock3,
  Command,
  Copy,
  Cpu,
  Download,
  Eye,
  Film,
  FolderOpen,
  Gauge,
  Grid2X2,
  HardDrive,
  Home,
  Image as ImageIcon,
  ImagePlus,
  Layers3,
  LayoutTemplate,
  Library,
  LockKeyhole,
  Maximize2,
  Menu,
  MoreHorizontal,
  Move3d,
  PanelLeftClose,
  PanelLeftOpen,
  PenLine,
  Play,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  UploadCloud,
  UserRound,
  Users,
  Video,
  Wand2,
  X,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { motion } from "framer-motion";
import { useMemo, useState, type ChangeEvent } from "react";

type View =
  | "overview"
  | "image"
  | "video"
  | "persona"
  | "motion"
  | "storyboard"
  | "assets"
  | "projects"
  | "settings";

type Toast = {
  title: string;
  message: string;
};

type NavItem = {
  id: View;
  label: string;
  icon: LucideIcon;
  badge?: string;
};

const navGroups: { label: string; items: NavItem[] }[] = [
  {
    label: "Workspace",
    items: [
      { id: "overview", label: "Overview", icon: Home },
      { id: "image", label: "Image studio", icon: ImageIcon },
      { id: "video", label: "Video studio", icon: Film, badge: "NEW" },
    ],
  },
  {
    label: "Build",
    items: [
      { id: "persona", label: "Personas", icon: UserRound },
      { id: "motion", label: "Motion control", icon: Move3d },
      { id: "storyboard", label: "Storyboard", icon: LayoutTemplate },
    ],
  },
  {
    label: "Library",
    items: [
      { id: "assets", label: "Assets", icon: Library },
      { id: "projects", label: "Projects", icon: FolderOpen },
    ],
  },
];

const projectCards = [
  { title: "Neon solitude", type: "Image sequence", date: "Just now", className: "project-neon", tag: "IMAGE" },
  { title: "The last horizon", type: "Cinematic film", date: "Yesterday", className: "project-horizon", tag: "VIDEO" },
  { title: "BROBOND / 01", type: "Character study", date: "Aug 21, 2024", className: "project-portrait", tag: "PERSONA" },
];

const imageSuggestions = ["cinematic portrait", "editorial fashion", "surreal landscape", "product campaign"];
const videoSuggestions = ["slow dolly in", "golden hour tracking", "handheld documentary", "orbital reveal"];

const storyboardScenes = [
  { scene: "01", title: "The arrival", description: "A lone figure steps into a luminous future city as the rain begins to fall.", duration: "04 sec", className: "scene-city" },
  { scene: "02", title: "Neon crossing", description: "He crosses the street beneath holographic signs and a passing electric train.", duration: "05 sec", className: "scene-neon" },
  { scene: "03", title: "A quiet signal", description: "A soft blue light reflects on his face as the city noise fades around him.", duration: "04 sec", className: "scene-signal" },
  { scene: "04", title: "Beyond the frame", description: "He looks up. The skyline opens into an infinite dawn, calm and weightless.", duration: "06 sec", className: "scene-dawn" },
];

const assetItems = [
  { title: "neon-solitude-01", meta: "PNG · 2048 × 2560", kind: "image", className: "asset-neon" },
  { title: "horizon-final-cut", meta: "MP4 · 00:15 · 1080p", kind: "video", className: "asset-horizon" },
  { title: "brobond-01-lora", meta: "LoRA · v1.2 · 142 MB", kind: "lora", className: "asset-lora" },
  { title: "city-rain-atmo", meta: "WAV · 00:38 · 48 kHz", kind: "audio", className: "asset-audio" },
  { title: "desert-ritual-study", meta: "JPG · 1600 × 900", kind: "image", className: "asset-desert" },
  { title: "orbit-camera-test", meta: "MP4 · 00:05 · 720p", kind: "video", className: "asset-orbit" },
];

function getViewLabel(view: View) {
  const item = navGroups.flatMap((group) => group.items).find((navItem) => navItem.id === view);
  return item?.label ?? "Overview";
}

function IconButton({
  label,
  children,
  onClick,
  className = "",
}: {
  label: string;
  children: React.ReactNode;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <button type="button" className={`icon-button ${className}`} aria-label={label} onClick={onClick}>
      {children}
    </button>
  );
}

function SectionTitle({ eyebrow, title, description }: { eyebrow?: string; title: string; description?: string }) {
  return (
    <div className="section-title">
      {eyebrow && <div className="eyebrow">{eyebrow}</div>}
      <h2>{title}</h2>
      {description && <p>{description}</p>}
    </div>
  );
}

function GradientArtwork({ className = "", label }: { className?: string; label?: string }) {
  return (
    <div className={`gradient-artwork ${className}`}>
      <div className="art-grain" />
      <div className="art-sun" />
      <div className="art-figure" />
      <div className="art-ground" />
      {label && <span className="art-label">{label}</span>}
    </div>
  );
}

function ModuleCard({
  title,
  description,
  icon: Icon,
  className,
  meta,
  onClick,
  visual,
}: {
  title: string;
  description: string;
  icon: LucideIcon;
  className: string;
  meta: string;
  onClick: () => void;
  visual: React.ReactNode;
}) {
  return (
    <button type="button" className={`module-card ${className}`} onClick={onClick}>
      <div className="module-visual">{visual}</div>
      <div className="module-info">
        <div className="module-icon"><Icon size={18} strokeWidth={1.8} /></div>
        <div className="module-copy">
          <div className="module-name">{title}<ArrowUpRight size={15} /></div>
          <p>{description}</p>
          <span className="module-meta">{meta}</span>
        </div>
      </div>
    </button>
  );
}

export default function StudioShell() {
  const [activeView, setActiveView] = useState<View>("overview");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [imagePrompt, setImagePrompt] = useState("A Brazilian athlete walking through a futuristic city at night");
  const [negativePrompt, setNegativePrompt] = useState("plastic skin, extra fingers, low detail");
  const [videoPrompt, setVideoPrompt] = useState("A lone traveler walks through a rain-soaked neon city, cinematic and slow");
  const [enhanced, setEnhanced] = useState(false);
  const [imageRatio, setImageRatio] = useState("3:4");
  const [videoRatio, setVideoRatio] = useState("16:9");
  const [videoType, setVideoType] = useState("Image to video");
  const [duration, setDuration] = useState("05s");
  const [selectedMotion, setSelectedMotion] = useState("Dolly in");
  const [selectedScene, setSelectedScene] = useState(0);
  const [assetFilter, setAssetFilter] = useState("All assets");
  const [generating, setGenerating] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [uploadedFile, setUploadedFile] = useState<string | null>(null);

  const activeLabel = useMemo(() => getViewLabel(activeView), [activeView]);

  const showToast = (title: string, message: string) => {
    setToast({ title, message });
    window.setTimeout(() => setToast(null), 4200);
  };

  const openView = (view: View) => {
    setActiveView(view);
    setMobileMenuOpen(false);
  };

  const startGeneration = (label: string) => {
    setGenerating(label);
    showToast("Render queued", `${label} is being prepared on your local GPU.`);
    window.setTimeout(() => {
      setGenerating(null);
      showToast("Render complete", `${label} is ready in your project library.`);
    }, 2200);
  };

  const handleUpload = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setUploadedFile(file.name);
      showToast("Reference added", `${file.name} is ready to guide your generation.`);
    }
  };

  const handleEnhancePrompt = () => {
    if (!enhanced) {
      setImagePrompt("Ultra-realistic Brazilian athletic man walking confidently through a luxury modern city at night, volumetric fog, teal and amber lighting, subtle film grain, IMAX composition, 85mm lens, natural skin texture, editorial fashion photography");
      setEnhanced(true);
      showToast("Prompt enhanced", "Your prompt now has cinematic direction and visual detail.");
    } else {
      setImagePrompt("A Brazilian athlete walking through a futuristic city at night");
      setEnhanced(false);
    }
  };

  const navigateToCreate = () => openView("image");

  return (
    <motion.div
      className="studio-app"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.45, ease: "easeOut" }}
    >
      <aside className={`sidebar ${sidebarCollapsed ? "sidebar-collapsed" : ""} ${mobileMenuOpen ? "mobile-open" : ""}`}>
        <div className="brand-row">
          <button type="button" className="brand" onClick={() => openView("overview")} aria-label="Go to overview">
            <span className="brand-mark"><span /></span>
            <span className="brand-wordmark">BROBOND<span>AI</span></span>
          </button>
          <IconButton label="Collapse sidebar" className="sidebar-toggle" onClick={() => setSidebarCollapsed((value) => !value)}>
            {sidebarCollapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
          </IconButton>
        </div>

        <div className="workspace-switcher">
          <div className="workspace-avatar">P</div>
          <div className="workspace-name"><strong>Personal studio</strong><span>Local workspace</span></div>
          <ChevronDown size={14} />
        </div>

        <nav className="sidebar-nav" aria-label="Main navigation">
          {navGroups.map((group) => (
            <div className="nav-group" key={group.label}>
              <div className="nav-label">{group.label}</div>
              {group.items.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`nav-item ${activeView === item.id ? "active" : ""}`}
                    onClick={() => openView(item.id)}
                    title={sidebarCollapsed ? item.label : undefined}
                  >
                    <Icon size={18} strokeWidth={activeView === item.id ? 2.1 : 1.7} />
                    <span>{item.label}</span>
                    {item.badge && <em>{item.badge}</em>}
                    {activeView === item.id && <span className="active-line" />}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="gpu-status">
            <div className="gpu-icon"><Cpu size={16} /></div>
            <div><strong>Local GPU</strong><span><i /> RTX 4090 · Ready</span></div>
            <Gauge size={15} className="gpu-gauge" />
          </div>
          <button type="button" className={`nav-item ${activeView === "settings" ? "active" : ""}`} onClick={() => openView("settings")}>
            <Settings2 size={18} strokeWidth={1.7} /><span>Settings</span>
          </button>
          <div className="profile-row">
            <div className="profile-avatar">PM</div>
            <div className="profile-copy"><strong>Petrick Martins</strong><span>Administrator</span></div>
            <MoreHorizontal size={17} />
          </div>
        </div>
      </aside>

      <div className="workspace-shell">
        <header className="topbar">
          <div className="topbar-left">
            <IconButton label="Open navigation" className="mobile-menu-button" onClick={() => setMobileMenuOpen((value) => !value)}><Menu size={19} /></IconButton>
            <div className="breadcrumbs"><span>Studio</span><ChevronRight size={13} /><strong>{activeLabel}</strong></div>
          </div>
          <div className="topbar-actions">
            <button type="button" className="command-search" onClick={() => showToast("Quick search", "Command search is ready for your next action.")}>
              <Search size={16} /><span>Search anything</span><kbd><Command size={11} /> K</kbd>
            </button>
            <div className="topbar-divider" />
            <IconButton label="Help center" onClick={() => showToast("Help center", "Guides and keyboard shortcuts are coming with the next release.")}><CircleHelp size={18} /></IconButton>
            <IconButton label="Notifications" onClick={() => showToast("All caught up", "There are no new studio notifications.")}><Bell size={18} /><span className="notification-dot" /></IconButton>
            <button type="button" className="top-avatar" onClick={() => openView("settings")}>PM</button>
          </div>
        </header>

        <main className="main-content">
          {activeView === "overview" && (
            <OverviewView onOpen={openView} onCreate={navigateToCreate} onToast={showToast} />
          )}
          {activeView === "image" && (
            <ImageStudioView
              prompt={imagePrompt}
              setPrompt={setImagePrompt}
              negativePrompt={negativePrompt}
              setNegativePrompt={setNegativePrompt}
              enhanced={enhanced}
              onEnhance={handleEnhancePrompt}
              ratio={imageRatio}
              setRatio={setImageRatio}
              uploadedFile={uploadedFile}
              onUpload={handleUpload}
              onGenerate={() => startGeneration("Image generation")}
              generating={generating === "Image generation"}
              onToast={showToast}
            />
          )}
          {activeView === "video" && (
            <VideoStudioView
              prompt={videoPrompt}
              setPrompt={setVideoPrompt}
              videoType={videoType}
              setVideoType={setVideoType}
              ratio={videoRatio}
              setRatio={setVideoRatio}
              duration={duration}
              setDuration={setDuration}
              onGenerate={() => startGeneration("Video generation")}
              generating={generating === "Video generation"}
              onToast={showToast}
            />
          )}
          {activeView === "persona" && <PersonaView onToast={showToast} onTrain={() => startGeneration("BROBOND / 01 LoRA training")} generating={generating === "BROBOND / 01 LoRA training"} />}
          {activeView === "motion" && <MotionView selectedMotion={selectedMotion} setSelectedMotion={setSelectedMotion} onGenerate={() => startGeneration("Motion control render")} generating={generating === "Motion control render"} onToast={showToast} />}
          {activeView === "storyboard" && <StoryboardView selectedScene={selectedScene} setSelectedScene={setSelectedScene} onGenerate={() => startGeneration("Storyboard sequence")} generating={generating === "Storyboard sequence"} onToast={showToast} />}
          {activeView === "assets" && <AssetsView filter={assetFilter} setFilter={setAssetFilter} onToast={showToast} />}
          {activeView === "projects" && <ProjectsView onOpen={openView} onToast={showToast} />}
          {activeView === "settings" && <SettingsView onToast={showToast} />}
        </main>
      </div>

      {toast && (
        <div className="toast" role="status">
          <div className="toast-icon"><Check size={16} /></div>
          <div><strong>{toast.title}</strong><span>{toast.message}</span></div>
          <button type="button" onClick={() => setToast(null)} aria-label="Close notification"><X size={15} /></button>
        </div>
      )}
    </motion.div>
  );
}

function OverviewView({ onOpen, onCreate, onToast }: { onOpen: (view: View) => void; onCreate: () => void; onToast: (title: string, message: string) => void }) {
  return (
    <div className="overview-page page-enter">
      <section className="welcome-banner">
        <div className="welcome-glow welcome-glow-one" />
        <div className="welcome-glow welcome-glow-two" />
        <div className="welcome-orbit orbit-one" />
        <div className="welcome-orbit orbit-two" />
        <div className="welcome-content">
          <div className="live-label"><span /> Local studio online</div>
          <h1>Create beyond<br /><em>the frame.</em></h1>
          <p>One private workspace for images, motion, characters and worlds that feel unmistakably yours.</p>
          <button type="button" className="primary-button light-button" onClick={onCreate}><Sparkles size={17} /> Start creating <ArrowRight size={15} /></button>
        </div>
        <div className="welcome-metrics">
          <div><strong>12</strong><span>Projects this week</span></div>
          <div><strong>4.8<span>k</span></strong><span>Frames generated</span></div>
          <div><strong>98<span>%</span></strong><span>GPU availability</span></div>
        </div>
        <div className="banner-mark">B<span>/</span>B</div>
      </section>

      <div className="page-heading overview-heading">
        <div><div className="eyebrow">Creative workspace</div><h2>What are you making today?</h2></div>
        <div className="heading-actions"><button type="button" className="secondary-button" onClick={() => onToast("Templates", "Your saved presets will appear here.")}><LayoutTemplate size={16} /> Browse templates</button><button type="button" className="icon-button bordered" aria-label="More options" onClick={() => onToast("Workspace menu", "More creation options are available from the module cards.")}><MoreHorizontal size={18} /></button></div>
      </div>

      <div className="module-grid">
        <ModuleCard title="Image studio" description="Craft stills with precision, texture and identity." icon={ImageIcon} className="module-image" meta="FLUX · 2048 px" onClick={() => onOpen("image")} visual={<div className="module-image-art"><div className="mini-sphere" /><div className="mini-person" /><span>01 / 04</span></div>} />
        <ModuleCard title="Video studio" description="Turn direction into cinematic moving worlds." icon={Film} className="module-video" meta="WAN 2.2 · 24 FPS" onClick={() => onOpen("video")} visual={<div className="module-video-art"><div className="video-sun" /><div className="video-mountain" /><div className="video-play"><Play size={14} fill="currentColor" /></div><span>00:05</span></div>} />
        <ModuleCard title="Personas" description="Keep your characters consistent, every frame." icon={UserRound} className="module-persona" meta="LoRA training · 01 active" onClick={() => onOpen("persona")} visual={<div className="module-persona-art"><div className="persona-face" /><div className="persona-ring" /><span>IDENTITY LOCKED</span></div>} />
        <ModuleCard title="Motion control" description="Direct the camera. Shape the feeling." icon={Move3d} className="module-motion" meta="9 camera paths" onClick={() => onOpen("motion")} visual={<div className="module-motion-art"><div className="motion-path path-a" /><div className="motion-path path-b" /><div className="motion-node node-a" /><div className="motion-node node-b" /><span>KEYFRAMES / 08</span></div>} />
        <ModuleCard title="Storyboard" description="Find the story before you render the scene." icon={LayoutTemplate} className="module-storyboard" meta="4 scenes · ready" onClick={() => onOpen("storyboard")} visual={<div className="module-story-art"><div /><div /><div /><div /><span>SCENE 01 — 04</span></div>} />
        <button type="button" className="module-card module-add" onClick={onCreate}><div className="add-icon"><Plus size={21} /></div><strong>Start from scratch</strong><span>Build a new creative project</span><ArrowUpRight size={17} /></button>
      </div>

      <div className="content-columns overview-lower">
        <section className="recent-section">
          <div className="section-bar"><div><div className="eyebrow">Your library</div><h3>Recent projects</h3></div><button type="button" className="text-button" onClick={() => onOpen("projects")}>View all <ArrowRight size={14} /></button></div>
          <div className="project-grid">
            {projectCards.map((project) => <button type="button" className="project-card" key={project.title} onClick={() => onToast("Project opened", `${project.title} is ready to continue.`)}><div className={`project-thumb ${project.className}`}><span className="project-tag">{project.tag}</span><span className="project-thumb-mark">B/B</span><MoreHorizontal size={16} /></div><div className="project-card-copy"><div><strong>{project.title}</strong><span>{project.type}</span></div><time>{project.date}</time></div></button>)}
          </div>
        </section>
        <aside className="queue-card">
          <div className="section-bar"><div><div className="eyebrow">Compute</div><h3>Render queue</h3></div><span className="queue-count">03</span></div>
          <div className="queue-progress"><div className="queue-progress-top"><span>Image variations</span><strong>68%</strong></div><div className="progress-track"><span style={{ width: "68%" }} /></div><small>RTX 4090 · ~42 sec remaining</small></div>
          <div className="queue-item"><div className="queue-item-icon"><Video size={15} /></div><div><strong>Horizon motion test</strong><span>Waiting · 15 sec</span></div><MoreHorizontal size={16} /></div>
          <div className="queue-item"><div className="queue-item-icon audio"><AudioWaveform size={15} /></div><div><strong>City rain atmosphere</strong><span>Waiting · WAV</span></div><MoreHorizontal size={16} /></div>
          <button type="button" className="queue-button" onClick={() => onToast("Queue manager", "All render jobs are running on this local workspace.")}>Open queue manager <ArrowUpRight size={14} /></button>
        </aside>
      </div>
    </div>
  );
}

function ImageStudioView({
  prompt,
  setPrompt,
  negativePrompt,
  setNegativePrompt,
  enhanced,
  onEnhance,
  ratio,
  setRatio,
  uploadedFile,
  onUpload,
  onGenerate,
  generating,
  onToast,
}: {
  prompt: string;
  setPrompt: (value: string) => void;
  negativePrompt: string;
  setNegativePrompt: (value: string) => void;
  enhanced: boolean;
  onEnhance: () => void;
  ratio: string;
  setRatio: (value: string) => void;
  uploadedFile: string | null;
  onUpload: (event: ChangeEvent<HTMLInputElement>) => void;
  onGenerate: () => void;
  generating: boolean;
  onToast: (title: string, message: string) => void;
}) {
  return (
    <div className="studio-page page-enter">
      <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-dot" /> Image generation</div><h1>Make the invisible <em>visible.</em></h1><p>Compose a still with depth, intention and your own visual language.</p></div><div className="heading-actions"><button type="button" className="secondary-button" onClick={() => onToast("Preset saved", "Your current image setup was saved as a reusable preset.")}><Copy size={15} /> Save preset</button><IconButton label="More image options" className="icon-button bordered" onClick={() => onToast("Image tools", "Upscale, variations and background removal are available after rendering.")}><MoreHorizontal size={18} /></IconButton></div></div>
      <div className="studio-layout image-layout">
        <section className="control-panel">
          <div className="panel-heading"><div><span className="panel-number">01</span><div><h3>Direction</h3><p>Tell the model what you see.</p></div></div><Wand2 size={17} /></div>
          <label className="field-label" htmlFor="image-prompt">Prompt <span>{prompt.length}/1000</span></label>
          <div className="prompt-editor"><textarea id="image-prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Describe your scene..." /><button type="button" className={`enhance-button ${enhanced ? "enhanced" : ""}`} onClick={onEnhance}><Sparkles size={14} /> {enhanced ? "Enhanced" : "Enhance prompt"}</button></div>
          <div className="suggestion-row">{imageSuggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => setPrompt(`${suggestion}, ${prompt}`)}>{suggestion}</button>)}</div>
          <label className="field-label" htmlFor="negative-prompt">Negative prompt <span>Optional</span></label>
          <input id="negative-prompt" className="text-input" value={negativePrompt} onChange={(event) => setNegativePrompt(event.target.value)} />
          <div className="panel-divider" />
          <div className="panel-heading compact"><div><span className="panel-number">02</span><div><h3>Composition</h3><p>Shape the visual output.</p></div></div><SlidersHorizontal size={17} /></div>
          <div className="field-row"><div><label className="field-label" htmlFor="model">Model</label><div className="select-wrap"><select id="model" className="select-field" defaultValue="FLUX.1 [dev]"><option>FLUX.1 [dev]</option><option>FLUX.1 [schnell]</option><option>SDXL · Cinematic</option></select><ChevronDown size={14} /></div></div><div><label className="field-label" htmlFor="lora">Character</label><div className="select-wrap"><select id="lora" className="select-field" defaultValue="BROBOND / 01"><option>BROBOND / 01</option><option>None</option></select><ChevronDown size={14} /></div></div></div>
          <div className="field-row"><div><label className="field-label">Aspect ratio</label><div className="segmented-control ratio-control">{["1:1", "3:4", "16:9", "9:16"].map((item) => <button type="button" key={item} className={ratio === item ? "selected" : ""} onClick={() => setRatio(item)}><span className={`ratio-icon ratio-${item.replace(":", "-")}`} />{item}</button>)}</div></div></div>
          <div className="field-row three-fields"><div><label className="field-label">Resolution</label><div className="select-wrap"><select className="select-field" defaultValue="2048 × 2560"><option>2048 × 2560</option><option>1024 × 1280</option><option>4096 × 5120</option></select><ChevronDown size={14} /></div></div><div><label className="field-label">Steps <span>28</span></label><input className="range-input" type="range" min="1" max="50" defaultValue="28" /></div><div><label className="field-label">CFG <span>6.5</span></label><input className="range-input" type="range" min="1" max="12" step="0.5" defaultValue="6.5" /></div></div>
          <div className="panel-divider" />
          <label className="field-label">Reference image <span>Optional</span></label>
          <label className={`upload-field ${uploadedFile ? "has-file" : ""}`} htmlFor="reference-upload"><input id="reference-upload" type="file" accept="image/*" onChange={onUpload} /><div className="upload-icon"><UploadCloud size={17} /></div><div><strong>{uploadedFile ?? "Drop an image or browse"}</strong><span>{uploadedFile ? "Reference ready · click to replace" : "PNG, JPG up to 10MB"}</span></div>{uploadedFile ? <Check size={16} /> : <Plus size={16} />}</label>
          <button type="button" className="primary-button generate-button" onClick={onGenerate} disabled={generating}>{generating ? <><RefreshCw size={17} className="spin" /> Rendering image...</> : <><Sparkles size={17} /> Generate image <span>⌘ ↵</span></>}</button>
        </section>
        <section className="preview-panel">
          <div className="preview-toolbar"><div><span className="panel-number">PREVIEW</span><strong>{generating ? "Rendering your direction" : "Your visual output"}</strong></div><div className="preview-tools"><span className="live-pill"><i /> {generating ? "Rendering" : "Live canvas"}</span><IconButton label="Fullscreen preview" onClick={() => onToast("Preview", "Fullscreen canvas is available in the desktop app.")}><Maximize2 size={16} /></IconButton><IconButton label="Preview options" onClick={() => onToast("Preview menu", "Export and variation controls are ready after your render.")}><MoreHorizontal size={16} /></IconButton></div></div>
          <div className="image-canvas-wrap"><div className={`image-canvas ${generating ? "is-rendering" : ""}`}><GradientArtwork className="hero-art" label="BROBOND / 01" />{generating && <div className="render-overlay"><div className="render-loader"><RefreshCw size={18} className="spin" /></div><strong>Building your frame</strong><span>Sampling light, texture and identity</span><div className="render-progress"><span /></div></div>}</div></div>
          <div className="preview-caption"><div><span>01</span><strong>{ratio} · {enhanced ? "Cinematic enhanced" : "Portrait study"}</strong></div><div><span>SEED</span><strong>482 019 77</strong></div><div><span>MODEL</span><strong>FLUX.1 [dev]</strong></div></div>
          <div className="preview-actions"><button type="button" className="secondary-button" onClick={() => onToast("Variation queued", "A new variation will use the same identity and composition.")}><RefreshCw size={15} /> Variations</button><button type="button" className="secondary-button" onClick={() => onToast("Upscale queued", "The 2× upscale has been added to the render queue.")}><Maximize2 size={15} /> Upscale 2×</button><button type="button" className="text-button" onClick={() => onToast("Export", "Choose a format after the image finishes rendering.")}><Download size={15} /> Export</button></div>
        </section>
      </div>
    </div>
  );
}

function VideoStudioView({
  prompt,
  setPrompt,
  videoType,
  setVideoType,
  ratio,
  setRatio,
  duration,
  setDuration,
  onGenerate,
  generating,
  onToast,
}: {
  prompt: string;
  setPrompt: (value: string) => void;
  videoType: string;
  setVideoType: (value: string) => void;
  ratio: string;
  setRatio: (value: string) => void;
  duration: string;
  setDuration: (value: string) => void;
  onGenerate: () => void;
  generating: boolean;
  onToast: (title: string, message: string) => void;
}) {
  return (
    <div className="studio-page page-enter">
      <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-dot video-dot" /> Video generation</div><h1>Give your idea <em>motion.</em></h1><p>Direct a moving image with camera language, timing and atmosphere.</p></div><div className="heading-actions"><span className="engine-status"><i /> WAN 2.2 engine ready</span><IconButton label="Video options" className="icon-button bordered" onClick={() => onToast("Video tools", "Start frame, end frame, native audio and export controls are ready.")}><MoreHorizontal size={18} /></IconButton></div></div>
      <div className="studio-layout video-layout">
        <section className="control-panel">
          <div className="panel-heading"><div><span className="panel-number">01</span><div><h3>Sequence</h3><p>Choose how the scene begins.</p></div></div><Clapperboard size={17} /></div>
          <div className="video-type-grid">{["Text to video", "Image to video", "Start + end frame"].map((item, index) => <button type="button" key={item} className={videoType === item ? "selected" : ""} onClick={() => setVideoType(item)}><span>{index === 0 ? <Wand2 size={16} /> : index === 1 ? <ImagePlus size={16} /> : <Layers3 size={16} />}</span>{item}<small>{index === 0 ? "From words" : index === 1 ? "Animate a still" : "Control both ends"}</small></button>)}</div>
          <label className="field-label" htmlFor="video-prompt">Motion direction <span>{prompt.length}/800</span></label>
          <div className="prompt-editor video-prompt-editor"><textarea id="video-prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} /><button type="button" className="enhance-button" onClick={() => { setPrompt(`${prompt}, cinematic camera movement, natural physics, subtle parallax, intentional pacing`); onToast("Direction expanded", "Camera language and motion detail were added."); }}><Sparkles size={14} /> Expand direction</button></div>
          <div className="suggestion-row">{videoSuggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => setPrompt(`${prompt}, ${suggestion}`)}>{suggestion}</button>)}</div>
          <div className="panel-divider" />
          <div className="panel-heading compact"><div><span className="panel-number">02</span><div><h3>Timing & frame</h3><p>Set the rhythm of the shot.</p></div></div><Clock3 size={17} /></div>
          <div className="field-row"><div><label className="field-label">Duration</label><div className="segmented-control">{["05s", "10s", "15s"].map((item) => <button type="button" key={item} className={duration === item ? "selected" : ""} onClick={() => setDuration(item)}>{item}</button>)}</div></div><div><label className="field-label">Frame rate</label><div className="select-wrap"><select className="select-field" defaultValue="24 fps"><option>24 fps</option><option>30 fps</option><option>60 fps</option></select><ChevronDown size={14} /></div></div></div>
          <div className="field-row"><div><label className="field-label">Aspect ratio</label><div className="segmented-control ratio-control">{["16:9", "9:16", "1:1"].map((item) => <button type="button" key={item} className={ratio === item ? "selected" : ""} onClick={() => setRatio(item)}><span className={`ratio-icon ratio-${item.replace(":", "-")}`} />{item}</button>)}</div></div></div>
          <label className="field-label">Camera motion</label><div className="motion-chip-row">{["Static", "Dolly in", "Orbit right", "Tracking"].map((item) => <button type="button" className={item === "Dolly in" ? "selected" : ""} key={item} onClick={() => onToast("Camera motion", `${item} camera path selected for this shot.`)}><Camera size={13} />{item}</button>)}</div>
          <div className="video-toggle-row"><div><strong><Zap size={15} /> Cinematic mode</strong><span>Depth-aware motion and film grain</span></div><span className="toggle on"><i /></span></div>
          <div className="video-toggle-row"><div><strong><AudioWaveform size={15} /> Native audio</strong><span>Generate a matching soundscape</span></div><span className="toggle"><i /></span></div>
          <button type="button" className="primary-button generate-button" onClick={onGenerate} disabled={generating}>{generating ? <><RefreshCw size={17} className="spin" /> Rendering sequence...</> : <><Video size={17} /> Generate video <span>⌘ ↵</span></>}</button>
        </section>
        <section className="preview-panel video-preview-panel">
          <div className="preview-toolbar"><div><span className="panel-number">SHOT 01 / 01</span><strong>{generating ? "Rendering cinematic sequence" : "Motion preview"}</strong></div><div className="preview-tools"><span className="live-pill"><i /> {duration} · {ratio}</span><IconButton label="Fullscreen video" onClick={() => onToast("Preview", "Fullscreen playback is available in the desktop app.")}><Maximize2 size={16} /></IconButton></div></div>
          <div className={`video-canvas ${generating ? "is-rendering" : ""}`}><div className="video-grid-lines" /><div className="video-portrait"><div className="portrait-halo" /><div className="portrait-head" /><div className="portrait-body" /></div><div className="video-title-card"><span>THE LAST HORIZON</span><strong>01:07:24:12</strong></div><div className="video-camera-label"><Camera size={13} /> DOLLY / 24 FPS</div>{generating && <div className="render-overlay"><div className="render-loader"><RefreshCw size={18} className="spin" /></div><strong>Rendering the shot</strong><span>Simulating camera movement and light</span><div className="render-progress"><span /></div></div>}</div>
          <div className="timeline"><div className="timeline-header"><span>Timeline</span><span>{duration} · 24 fps</span></div><div className="timeline-track"><span className="timeline-fill" /><i className="timeline-cursor" /></div><div className="timeline-ticks"><span>00:00</span><span>00:02</span><span>00:04</span><span>00:05</span></div></div>
          <div className="preview-actions"><button type="button" className="secondary-button play-button" onClick={() => onToast("Playback", "Preview playback started.")}><Play size={15} fill="currentColor" /> Play preview</button><button type="button" className="text-button" onClick={() => onToast("Export", "MP4 H.264 export will be available after rendering.")}><Download size={15} /> Export MP4</button></div>
        </section>
      </div>
    </div>
  );
}

function PersonaView({ onToast, onTrain, generating }: { onToast: (title: string, message: string) => void; onTrain: () => void; generating: boolean }) {
  return (
    <div className="studio-page page-enter">
      <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-dot persona-dot" /> Character consistency</div><h1>Your identity, <em>in every frame.</em></h1><p>Train a private character model once. Direct it everywhere.</p></div><div className="heading-actions"><button type="button" className="secondary-button" onClick={() => onToast("Persona guide", "Add 20–50 varied photos for the most consistent LoRA.")}><CircleHelp size={15} /> Training guide</button></div></div>
      <div className="persona-overview-grid">
        <section className="persona-profile-card"><div className="persona-cover"><div className="cover-orb" /><div className="cover-lines" /><span>IDENTITY / 01</span></div><div className="persona-profile-content"><div className="large-persona-avatar"><div className="persona-avatar-head" /><div className="persona-avatar-body" /></div><div className="persona-profile-top"><div><div className="verified-label"><ShieldCheck size={14} /> Identity verified</div><h2>BROBOND / 01</h2><p>Signature character · Created 14 Aug 2024</p></div><button type="button" className="icon-button bordered" onClick={() => onToast("Persona editor", "Edit identity details and visual anchors.")}><PenLine size={16} /></button></div><div className="persona-bio">Brazilian athletic man with a grounded presence, tied-back hair and a short beard. Built for natural, cinematic storytelling.</div><div className="persona-details"><div><span>Age</span><strong>50 years</strong></div><div><span>Height</span><strong>1.85 m</strong></div><div><span>Eyes</span><strong>Deep brown</strong></div><div><span>Style</span><strong>Editorial / real</strong></div></div><div className="identity-score"><div><span>Identity consistency</span><strong>94%</strong></div><div className="progress-track"><span style={{ width: "94%" }} /></div><small>Excellent across 38 generated frames</small></div></div></section>
        <section className="persona-training-card"><div className="section-bar"><div><div className="eyebrow">Training set</div><h3>Reference photos</h3></div><span className="photo-count">24 / 50</span></div><div className="photo-grid">{["photo-a", "photo-b", "photo-c", "photo-d", "photo-e", "photo-f", "photo-g", "photo-h", "photo-i", "photo-j", "photo-k", "photo-l"].map((photo, index) => <div className={`reference-photo ${photo}`} key={photo}><span>{String(index + 1).padStart(2, "0")}</span></div>)}<label className="add-photo"><input type="file" accept="image/*" multiple onChange={() => onToast("Photos added", "New reference photos were added to the training set.")} /><Plus size={19} /><span>Add photos</span></label></div><div className="training-status"><div className="training-status-icon"><Check size={16} /></div><div><strong>Ready to train</strong><span>Good variety across angles, lighting and expressions</span></div><button type="button" className="text-button" onClick={() => onToast("Training set", "Your 24 photos cover all recommended identity angles.")}>Review <ArrowRight size={14} /></button></div><button type="button" className="primary-button train-button" onClick={onTrain} disabled={generating}>{generating ? <><RefreshCw size={17} className="spin" /> Training LoRA...</> : <><Sparkles size={17} /> Train character LoRA <span>~18 min</span></>}</button></section>
      </div>
      <div className="content-columns persona-lower"><section className="settings-card"><div className="section-bar"><div><div className="eyebrow">Identity anchors</div><h3>What makes them, them.</h3></div><button type="button" className="text-button" onClick={() => onToast("Identity anchors", "Anchor editing is available for this persona.")}><PenLine size={14} /> Edit</button></div><div className="anchor-list"><div className="anchor-row"><div className="anchor-icon"><UserRound size={15} /></div><div><strong>Appearance</strong><span>Short tied-back hair · short beard · athletic build</span></div><Check size={15} /></div><div className="anchor-row"><div className="anchor-icon"><Eye size={15} /></div><div><strong>Expression</strong><span>Calm gaze · confident presence · natural smile</span></div><Check size={15} /></div><div className="anchor-row"><div className="anchor-icon"><Sparkles size={15} /></div><div><strong>Signature style</strong><span>Quiet luxury · monochrome tailoring · tactile fabrics</span></div><Check size={15} /></div></div></section><section className="usage-card"><div className="eyebrow">Model usage</div><div className="usage-number">38 <span>renders</span></div><div className="usage-chart"><span style={{ height: "38%" }} /><span style={{ height: "58%" }} /><span style={{ height: "45%" }} /><span style={{ height: "76%" }} /><span style={{ height: "62%" }} /><span style={{ height: "91%" }} /><span style={{ height: "72%" }} /><span style={{ height: "100%" }} /><span style={{ height: "84%" }} /><span style={{ height: "92%" }} /></div><div className="usage-footer"><span>Last 30 days</span><strong>+24%</strong></div></section></div>
    </div>
  );
}

function MotionView({ selectedMotion, setSelectedMotion, onGenerate, generating, onToast }: { selectedMotion: string; setSelectedMotion: (value: string) => void; onGenerate: () => void; generating: boolean; onToast: (title: string, message: string) => void }) {
  const motions = [
    ["Dolly in", "Push closer", "motion-dolly"],
    ["Dolly out", "Reveal space", "motion-dolly-out"],
    ["Orbit left", "Circle subject", "motion-orbit-left"],
    ["Orbit right", "Circle subject", "motion-orbit-right"],
    ["Crane up", "Rise above", "motion-crane"],
    ["Handheld", "Human texture", "motion-handheld"],
    ["Static", "Hold the frame", "motion-static"],
    ["Tracking", "Follow subject", "motion-track"],
  ];
  return (
    <div className="studio-page page-enter">
      <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-dot motion-dot" /> Direction system</div><h1>Move with <em>intention.</em></h1><p>Build a camera path, set the keyframes and let the scene breathe.</p></div><div className="heading-actions"><span className="keyframe-pill"><span /> 8 keyframes auto-generated</span><IconButton label="Motion options" className="icon-button bordered" onClick={() => onToast("Motion tools", "Use the camera presets to build a path for your scene.")}><MoreHorizontal size={18} /></IconButton></div></div>
      <div className="motion-layout"><section className="motion-canvas-panel"><div className="preview-toolbar"><div><span className="panel-number">CAMERA PATH / 01</span><strong>Neon solitude · motion pass</strong></div><div className="preview-tools"><span className="live-pill"><i /> 3D camera</span><IconButton label="Fullscreen motion canvas" onClick={() => onToast("Motion canvas", "Fullscreen camera path view is available in the desktop app.")}><Maximize2 size={16} /></IconButton></div></div><div className="motion-canvas"><div className="motion-scene"><div className="motion-sun" /><div className="motion-city city-a" /><div className="motion-city city-b" /><div className="motion-subject" /><div className="motion-floor" /></div><div className="camera-path"><span className="camera-line" /><i className="camera-node node-1" /><i className="camera-node node-2" /><i className="camera-node node-3" /><i className="camera-node node-4" /></div><div className="motion-axis"><span>X</span><span>Y</span><span>Z</span></div><span className="scene-coordinates">X 1.24 · Y 0.68 · Z 4.90</span></div><div className="keyframe-timeline"><div className="timeline-header"><span>Keyframe timeline</span><span>00:00 — 00:05</span></div><div className="keyframe-track"><span className="track-line" /><i className="keyframe k1" /><i className="keyframe k2" /><i className="keyframe k3" /><i className="keyframe k4" /><i className="keyframe k5" /></div><div className="timeline-ticks"><span>00:00</span><span>00:01</span><span>00:02</span><span>00:03</span><span>00:04</span><span>00:05</span></div></div></section><aside className="motion-controls"><div className="panel-heading"><div><span className="panel-number">01</span><div><h3>Camera preset</h3><p>Start with a movement.</p></div></div><Move3d size={17} /></div><div className="motion-presets">{motions.map(([title, subtitle, className]) => <button type="button" key={title} className={selectedMotion === title ? "selected" : ""} onClick={() => setSelectedMotion(title)}><span className={`motion-icon ${className}`}><i /></span><strong>{title}</strong><small>{subtitle}</small>{selectedMotion === title && <Check size={14} />}</button>)}</div><div className="panel-divider" /><div className="panel-heading compact"><div><span className="panel-number">02</span><div><h3>Fine tune</h3><p>Make the path yours.</p></div></div><SlidersHorizontal size={17} /></div><div className="fine-tune"><label>Intensity <span>72%</span></label><input className="range-input" type="range" defaultValue="72" /><label>Smoothing <span>Soft</span></label><input className="range-input" type="range" defaultValue="84" /><label>Ease <span>In / out</span></label><div className="select-wrap"><select className="select-field" defaultValue="Cubic"><option>Cubic</option><option>Linear</option><option>Spring</option></select><ChevronDown size={14} /></div></div><button type="button" className="primary-button generate-button" onClick={onGenerate} disabled={generating}>{generating ? <><RefreshCw size={17} className="spin" /> Rendering motion...</> : <><Move3d size={17} /> Generate motion <span>⌘ ↵</span></>}</button></aside></div>
    </div>
  );
}

function StoryboardView({ selectedScene, setSelectedScene, onGenerate, generating, onToast }: { selectedScene: number; setSelectedScene: (value: number) => void; onGenerate: () => void; generating: boolean; onToast: (title: string, message: string) => void }) {
  return (
    <div className="studio-page page-enter">
      <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-dot story-dot" /> Narrative design</div><h1>See the story <em>before it moves.</em></h1><p>Turn a simple idea into a sequence of intentional, connected frames.</p></div><div className="heading-actions"><button type="button" className="secondary-button" onClick={() => onToast("Storyboard saved", "Your sequence was saved to the project library.")}><FolderOpen size={15} /> Save storyboard</button></div></div>
      <section className="story-input-panel"><div className="story-input-copy"><div className="eyebrow">Story seed</div><h3>What should we feel?</h3><p>Start with a sentence. The prompt engine will find the rhythm.</p></div><div className="story-input-area"><textarea defaultValue="A man walks alone through a futuristic city at night, searching for a signal from home." /><div className="story-input-footer"><span><Sparkles size={14} /> Narrative engine · ready</span><button type="button" className="primary-button small-button" onClick={onGenerate} disabled={generating}>{generating ? <><RefreshCw size={15} className="spin" /> Building scenes</> : <><Wand2 size={15} /> Generate sequence</>}</button></div></div></section>
      <div className="storyboard-header"><div><div className="eyebrow">Generated sequence</div><h2>Four beats, one feeling.</h2></div><div className="storyboard-meta"><span><Check size={14} /> 4 connected scenes</span><span>19 sec total</span></div></div>
      <div className="storyboard-layout"><div className="scene-list">{storyboardScenes.map((scene, index) => <button type="button" className={`scene-card ${selectedScene === index ? "selected" : ""}`} key={scene.scene} onClick={() => setSelectedScene(index)}><div className={`scene-thumb ${scene.className}`}><span>{scene.scene}</span><div className="scene-thumb-subject" /></div><div className="scene-card-copy"><div className="scene-card-top"><span>Scene {scene.scene}</span><span>{scene.duration}</span></div><h3>{scene.title}</h3><p>{scene.description}</p><div className="scene-card-footer"><span><Sparkles size={12} /> Prompt ready</span><ArrowUpRight size={14} /></div></div></button>)}</div><aside className="scene-detail"><div className="scene-detail-top"><div><span className="panel-number">SCENE {storyboardScenes[selectedScene].scene}</span><h3>{storyboardScenes[selectedScene].title}</h3></div><IconButton label="Scene options" onClick={() => onToast("Scene options", "Duplicate, reorder and edit this scene from the full editor.")}><MoreHorizontal size={17} /></IconButton></div><div className={`scene-detail-art ${storyboardScenes[selectedScene].className}`}><div className="detail-art-grid" /><div className="detail-art-subject" /><span>FRAME PREVIEW</span></div><label className="field-label">Scene prompt <span>Editable</span></label><textarea className="scene-prompt" defaultValue={`${storyboardScenes[selectedScene].description} Cinematic composition, tactile rain, deep cobalt shadows, controlled camera movement, 35mm lens.`} /><div className="scene-detail-actions"><button type="button" className="secondary-button" onClick={() => onToast("Scene prompt", "Prompt copied to clipboard.")}><Copy size={15} /> Copy prompt</button><button type="button" className="text-button" onClick={() => onToast("Scene render", "This scene was added to the render queue.")}><Sparkles size={14} /> Render scene</button></div></aside></div>
    </div>
  );
}

function AssetsView({ filter, setFilter, onToast }: { filter: string; setFilter: (value: string) => void; onToast: (title: string, message: string) => void }) {
  const filters = ["All assets", "Images", "Videos", "Audio", "LoRAs"];
  const visibleAssets = assetItems.filter((asset) => filter === "All assets" || (filter === "Images" && asset.kind === "image") || (filter === "Videos" && asset.kind === "video") || (filter === "Audio" && asset.kind === "audio") || (filter === "LoRAs" && asset.kind === "lora"));
  return (
    <div className="studio-page page-enter"><div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-dot assets-dot" /> Your library</div><h1>Everything you <em>made.</em></h1><p>A calm home for your images, films, sounds, models and ideas.</p></div><div className="heading-actions"><button type="button" className="secondary-button" onClick={() => onToast("New folder", "A new folder can organize your next creative direction.")}><Plus size={15} /> New folder</button><button type="button" className="primary-button small-button" onClick={() => onToast("Upload", "Upload files directly into your local asset library.")}><UploadCloud size={15} /> Upload</button></div></div><div className="asset-toolbar"><div className="asset-filters">{filters.map((item) => <button type="button" key={item} className={filter === item ? "selected" : ""} onClick={() => setFilter(item)}>{item}{item === "All assets" && <span>24</span>}</button>)}</div><div className="asset-toolbar-right"><div className="asset-search"><Search size={15} /><input placeholder="Search assets" /><kbd>/</kbd></div><IconButton label="Grid view" className="active"><Grid2X2 size={16} /></IconButton><IconButton label="Sort assets" onClick={() => onToast("Sort assets", "Assets are currently sorted by most recent.")}><SlidersHorizontal size={16} /></IconButton></div></div><div className="folder-path"><FolderOpen size={15} /><span>Library</span><ChevronRight size={13} /><strong>All assets</strong><span className="path-spacer" /><span>Updated just now</span></div><div className="assets-grid">{visibleAssets.map((asset) => <button type="button" className="asset-card" key={asset.title} onClick={() => onToast("Asset selected", `${asset.title} is ready for your next composition.`)}><div className={`asset-preview ${asset.className}`}><span className="asset-kind">{asset.kind === "lora" ? "MODEL" : asset.kind.toUpperCase()}</span>{asset.kind === "video" && <span className="asset-play"><Play size={13} fill="currentColor" /></span>}{asset.kind === "audio" && <div className="asset-wave"><i /><i /><i /><i /><i /><i /><i /><i /><i /></div>}<span className="asset-more"><MoreHorizontal size={15} /></span></div><div className="asset-card-copy"><strong>{asset.title}</strong><span>{asset.meta}</span></div></button>)}</div></div>
  );
}

function ProjectsView({ onOpen, onToast }: { onOpen: (view: View) => void; onToast: (title: string, message: string) => void }) {
  return (
    <div className="studio-page page-enter"><div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-dot project-dot" /> Creative archive</div><h1>Projects with a <em>pulse.</em></h1><p>Return to a direction, pick up a thread or start something new.</p></div><div className="heading-actions"><button type="button" className="secondary-button" onClick={() => onToast("Project filter", "Showing all active projects.")}><SlidersHorizontal size={15} /> Filter</button><button type="button" className="primary-button small-button" onClick={() => onOpen("image")}><Plus size={15} /> New project</button></div></div><div className="project-summary"><div><span>Active projects</span><strong>12</strong><small>+3 this month</small></div><div><span>Frames generated</span><strong>4.8k</strong><small>Across all projects</small></div><div><span>Storage used</span><strong>68<span> GB</span></strong><small>of 500 GB local</small></div><div className="summary-chart"><span style={{ height: "32%" }} /><span style={{ height: "48%" }} /><span style={{ height: "42%" }} /><span style={{ height: "66%" }} /><span style={{ height: "58%" }} /><span style={{ height: "83%" }} /><span style={{ height: "74%" }} /><span style={{ height: "92%" }} /></div></div><div className="projects-table"><div className="table-header"><span>Project</span><span>Type</span><span>Last edited</span><span>Status</span><span /></div>{[{ title: "Neon solitude", type: "Image sequence", edited: "Just now", status: "In progress", className: "project-neon" }, { title: "The last horizon", type: "Cinematic film", edited: "Yesterday", status: "Ready", className: "project-horizon" }, { title: "BROBOND / 01", type: "Character study", edited: "Aug 21, 2024", status: "Ready", className: "project-portrait" }, { title: "Desert ritual", type: "Storyboard", edited: "Aug 18, 2024", status: "Draft", className: "project-desert" }, { title: "Signal / 04", type: "Video experiment", edited: "Aug 12, 2024", status: "Ready", className: "project-signal" }].map((project) => <button type="button" className="table-row" key={project.title} onClick={() => onToast("Project opened", `${project.title} is ready to continue.`)}><div className="table-project"><div className={`table-thumb ${project.className}`} /><strong>{project.title}</strong></div><span>{project.type}</span><span>{project.edited}</span><span className={`status ${project.status.toLowerCase().replace(" ", "-")}`}><i />{project.status}</span><MoreHorizontal size={17} /></button>)}</div></div>
  );
}

function SettingsView({ onToast }: { onToast: (title: string, message: string) => void }) {
  return (
    <div className="studio-page page-enter"><div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-dot settings-dot" /> Workspace preferences</div><h1>Make it <em>yours.</em></h1><p>Local-first controls for the way BROBOND works with you.</p></div><button type="button" className="primary-button small-button" onClick={() => onToast("Settings saved", "Your workspace preferences are up to date.")}><Check size={15} /> Save changes</button></div><div className="settings-layout"><aside className="settings-nav"><button type="button" className="selected"><Settings2 size={16} /> General</button><button type="button"><Cpu size={16} /> Compute</button><button type="button"><ShieldCheck size={16} /> Privacy & security</button><button type="button"><FolderOpen size={16} /> Storage</button><button type="button"><Bell size={16} /> Notifications</button></aside><section className="settings-content"><div className="settings-block"><div className="settings-block-title"><div><div className="eyebrow">General</div><h3>Studio defaults</h3></div><span>Saved locally</span></div><div className="settings-form-row"><div><strong>Interface theme</strong><span>Keep the studio dark and focused.</span></div><div className="theme-options"><button type="button" className="theme-option selected"><span className="theme-dark" />Dark</button><button type="button" className="theme-option" onClick={() => onToast("Theme", "Light theme is planned for a future release.")}><span className="theme-light" />Light</button></div></div><div className="settings-form-row"><div><strong>Default image model</strong><span>Used whenever you start a new image.</span></div><div className="select-wrap settings-select"><select className="select-field" defaultValue="FLUX.1 [dev]"><option>FLUX.1 [dev]</option><option>FLUX.1 [schnell]</option></select><ChevronDown size={14} /></div></div><div className="settings-form-row"><div><strong>Autosave projects</strong><span>Keep every creative decision recoverable.</span></div><span className="toggle on"><i /></span></div></div><div className="settings-block"><div className="settings-block-title"><div><div className="eyebrow">Local compute</div><h3>RTX 4090</h3></div><span className="ready-text"><i /> Ready</span></div><div className="compute-card"><div className="compute-stat"><Cpu size={17} /><span>GPU memory</span><strong>18.4 <small>/ 24 GB</small></strong><div className="progress-track"><span style={{ width: "77%" }} /></div></div><div className="compute-stat"><HardDrive size={17} /><span>Model cache</span><strong>142 <small>/ 500 GB</small></strong><div className="progress-track"><span style={{ width: "28%" }} /></div></div><div className="compute-stat"><Gauge size={17} /><span>Temperature</span><strong>64° <small>Celsius</small></strong><div className="temp-line"><span /></div></div></div></div><div className="settings-block danger-block"><div><div className="eyebrow">Privacy</div><h3>Private by default.</h3><p>Your prompts, reference images and outputs stay on this machine. Nothing leaves this workspace unless you export it.</p></div><div className="privacy-lock"><LockKeyhole size={18} /><span>Local only</span></div></div></section></div></div>
  );
}
