'use client';

/**
 * PR012 — ETAPA 4: the Hero Workspace.
 *
 * Replaces the two empty panels with a real working pair:
 *  - left: the Creative Brief (textarea, scene count, language, platform,
 *    one primary action);
 *  - right: the Live Storyboard Preview — scene thumbnails shown even
 *    before anything renders, using cinematic gradient placeholders so
 *    the workspace never looks empty.
 *
 * This is presentational only: the caller supplies the brief state and
 * the `onSubmit` callback, and can wire it directly to
 * `createProductionPlan` / `directIntent` (both already exist in
 * `lib/api.ts`, untouched by this PR).
 */
import { Clapperboard, Film, Sparkles } from 'lucide-react';

export type HeroWorkspaceScenePreview = {
  id: string;
  sceneNumber: number;
  title: string;
  mood?: string;
  thumbnailUrl?: string | null;
};

export type HeroWorkspaceProps = {
  brief: string;
  onBriefChange: (value: string) => void;
  sceneCount: number;
  onSceneCountChange: (value: number) => void;
  language: string;
  onLanguageChange: (value: string) => void;
  platform: string;
  onPlatformChange: (value: string) => void;
  onSubmit: () => void;
  submitting?: boolean;
  scenes: HeroWorkspaceScenePreview[];
  languageOptions?: { value: string; label: string }[];
  platformOptions?: { value: string; label: string }[];
};

const DEFAULT_LANGUAGES = [
  { value: 'pt-BR', label: 'Português (BR)' },
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Español' },
];

const DEFAULT_PLATFORMS = [
  { value: 'instagram', label: 'Instagram' },
  { value: 'reels', label: 'Reels' },
  { value: 'tiktok', label: 'TikTok' },
  { value: 'youtube', label: 'YouTube' },
  { value: 'cinema', label: 'Cinema' },
];

export function HeroWorkspace({
  brief,
  onBriefChange,
  sceneCount,
  onSceneCountChange,
  language,
  onLanguageChange,
  platform,
  onPlatformChange,
  onSubmit,
  submitting = false,
  scenes,
  languageOptions = DEFAULT_LANGUAGES,
  platformOptions = DEFAULT_PLATFORMS,
}: HeroWorkspaceProps) {
  return (
    <section className="bb-hero-workspace" aria-label="Creative workspace">
      <div className="bb-hero-panel bb-hero-brief" aria-label="Creative brief panel">
        <div className="bb-hero-panel-heading">
          <span className="bb-hero-panel-number">01</span>
          <div>
            <h3>Creative Brief</h3>
            <p>Diga o que você quer criar — o Director cuida da direção.</p>
          </div>
        </div>

        <label className="bb-field-label" htmlFor="bb-hero-brief-textarea">
          Brief <span>{brief.length} caracteres</span>
        </label>
        <textarea
          id="bb-hero-brief-textarea"
          className="bb-hero-textarea"
          value={brief}
          onChange={event => onBriefChange(event.target.value)}
          placeholder="Descreva a cena, o produto ou a intenção criativa..."
          aria-label="Creative brief"
        />

        <div className="bb-hero-field-row">
          <label className="bb-field-label" htmlFor="bb-hero-scene-count">
            Cenas
            <input
              id="bb-hero-scene-count"
              type="number"
              min={1}
              max={12}
              value={sceneCount}
              onChange={event => onSceneCountChange(Number(event.target.value))}
            />
          </label>

          <label className="bb-field-label" htmlFor="bb-hero-language">
            Idioma
            <select id="bb-hero-language" value={language} onChange={event => onLanguageChange(event.target.value)}>
              {languageOptions.map(option => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>

          <label className="bb-field-label" htmlFor="bb-hero-platform">
            Plataforma
            <select id="bb-hero-platform" value={platform} onChange={event => onPlatformChange(event.target.value)}>
              {platformOptions.map(option => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
        </div>

        <button
          type="button"
          className="bb-primary-button bb-hero-submit"
          onClick={onSubmit}
          disabled={submitting || !brief.trim()}
        >
          <Sparkles size={16} aria-hidden="true" /> {submitting ? 'Dirigindo…' : 'Criar Produção'}
        </button>
      </div>

      <div className="bb-hero-panel bb-hero-preview" aria-label="Live storyboard preview">
        <div className="bb-hero-panel-heading">
          <span className="bb-hero-panel-number"><Clapperboard size={15} aria-hidden="true" /></span>
          <div>
            <h3>Live Storyboard Preview</h3>
            <p>{scenes.length ? `${scenes.length} cenas prontas para direção` : 'Aguardando o primeiro brief'}</p>
          </div>
        </div>

        {scenes.length === 0 ? (
          <div className="bb-hero-preview-empty">
            <Film size={22} aria-hidden="true" />
            <strong>Nenhuma cena ainda</strong>
            <span>As miniaturas cinematográficas aparecem aqui assim que você criar a produção.</span>
          </div>
        ) : (
          <ul className="bb-hero-preview-grid" role="list">
            {scenes.map((scene, index) => (
              <li key={scene.id} className="bb-hero-preview-item">
                <div className={`bb-hero-preview-thumb bb-hero-preview-thumb-${index % 6}`}>
                  {scene.thumbnailUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={scene.thumbnailUrl} alt={`Preview of ${scene.title}`} />
                  ) : (
                    <span className="bb-hero-preview-placeholder-label">SCENE {String(scene.sceneNumber).padStart(2, '0')}</span>
                  )}
                </div>
                <div className="bb-hero-preview-meta">
                  <strong>{scene.title}</strong>
                  {scene.mood && <span>{scene.mood}</span>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

export default HeroWorkspace;
