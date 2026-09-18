'use client';

/**
 * PR009.6.1 — Pixel Perfect Login: the hero column (58% of the viewport).
 *
 * Reproduces the approved mockup exactly. The official photograph
 * (/brand/login-hero.jpg) fills the whole column with `object-fit: cover`
 * and `object-position: 50% 28%` so the founder's face is never cropped.
 * Above it, in this order: a black tint at 42%, a gold radial coming from
 * the top-right corner, an edge vignette, and a bottom shade that anchors
 * the copy. The previous brand-film upgrade is gone — the mockup is the
 * photograph, and nothing may reinterpret it.
 *
 * The column is a three-row grid (top bar / centred brand block / footer
 * cards), so the five pillar cards can never overlap the copy.
 */
import LoginFeatures from './login-features';
import type { LoginCopy } from './login-copy';

export function LoginHeroPanel({ copy }: { copy: LoginCopy }) {
  return (
    <aside className="bb-login-hero" aria-label={copy.heroAlt}>
      {/* Photo + overlay stack. Decorative: the column carries the label. */}
      <div className="bb-login-hero-media" aria-hidden="true">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img className="bb-login-hero-photo" src="/brand/login-hero.jpg" alt="" />
        <div className="bb-login-hero-tint" />
        <div className="bb-login-hero-sun" />
        <div className="bb-login-hero-gold" />
        <div className="bb-login-hero-vignette" />
        <div className="bb-login-hero-shade" />
      </div>

      {/* Top bar: brand line left, manifesto right. */}
      <div className="bb-login-hero-topbar">
        <span className="bb-login-hero-topbar-left">{copy.topBar}</span>
        <span className="bb-login-hero-topbar-right">
          <i aria-hidden="true" />
          {copy.topBarRight}
        </span>
      </div>

      {/* Centre-bottom brand block: logo 420px, título, subtítulo. */}
      <div className="bb-login-hero-content">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img className="bb-login-hero-logo" src="/brand/brobond-logo-light.png" alt="Brobond Wear" />
        <h1 className="bb-login-hero-title">
          {copy.titleLead}
          <span>{copy.titleAccent}</span>
        </h1>
        <p className="bb-login-hero-subtitle">{copy.subtitle}</p>
      </div>

      {/* Hero footer: the five equal cards, then the accent tagline. */}
      <div className="bb-login-hero-footer">
        <LoginFeatures copy={copy} />
        <p className="bb-login-hero-tagline">
          <i aria-hidden="true" />
          {copy.tagline}
        </p>
      </div>
    </aside>
  );
}

export default LoginHeroPanel;
