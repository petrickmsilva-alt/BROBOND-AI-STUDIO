'use client';

/**
 * PR009.6 — the login hero column.
 *
 * The official founder photograph (/brand/login-hero.jpg) is the backdrop:
 * black tint 55%, a very soft gold radial and blur only at the edges, so
 * the center keeps its cinematic contrast. On powerful desktops the same
 * column upgrades to the 11-second brand film (/brand/login-hero.mp4 —
 * RAM ao pôr do sol, bastidores Brobond) with the photograph as the
 * universal fallback: the film fades in only after `canplay`, and any
 * error leaves the photograph exactly where it was. No device ever sees
 * an empty column, and `prefers-reduced-motion` is respected before the
 * film is even mounted.
 */
import { useEffect, useState } from 'react';
import LoginFeatures from './login-features';
import type { LoginCopy } from './login-copy';

type NetworkInformation = { saveData?: boolean; effectiveType?: string };

/** "Desktop potente": laptop-width, hover pointer, motion allowed, 4+
 *  logical cores and no data-saver / 2G connection. Anything else — every
 *  tablet and phone, every reduced-motion preference — gets the photo. */
function filmAllowedHere(): boolean {
  if (typeof window === 'undefined') return false;
  const desktop = window.matchMedia(
    '(min-width: 1024px) and (hover: hover) and (prefers-reduced-motion: no-preference)',
  );
  if (!desktop.matches) return false;
  if ((window.navigator.hardwareConcurrency ?? 4) < 4) return false;
  const connection = (window.navigator as Navigator & { connection?: NetworkInformation }).connection;
  return !(connection?.saveData === true || connection?.effectiveType === '2g');
}

export function LoginHeroPanel({ copy }: { copy: LoginCopy }) {
  const [filmAllowed, setFilmAllowed] = useState(false);
  const [filmReady, setFilmReady] = useState(false);

  useEffect(() => {
    const desktop = window.matchMedia(
      '(min-width: 1024px) and (hover: hover) and (prefers-reduced-motion: no-preference)',
    );
    const sync = () => setFilmAllowed(filmAllowedHere());
    sync();
    desktop.addEventListener('change', sync);
    return () => desktop.removeEventListener('change', sync);
  }, []);

  return (
    <aside className="bb-login-hero" aria-label={copy.heroAlt}>
      <div className="bb-login-hero-banner">
        <div className="bb-login-hero-media" aria-hidden="true">
          {/* The official photograph: always present, always the fallback. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="bb-login-hero-photo" src="/brand/login-hero.jpg" alt="" />
          {filmAllowed && (
            <video
              className={`bb-login-hero-film${filmReady ? ' is-ready' : ''}`}
              src="/brand/login-hero.mp4"
              autoPlay
              muted
              loop
              playsInline
              preload="auto"
              onCanPlay={() => setFilmReady(true)}
              onError={() => setFilmReady(false)}
            />
          )}
          {/* Overlay stack: black 55% → soft gold radial → edge-only blur →
              bottom shade that anchors the copy and the feature row. */}
          <div className="bb-login-hero-tint" />
          <div className="bb-login-hero-gold" />
          <div className="bb-login-hero-blur bb-login-hero-blur-x" />
          <div className="bb-login-hero-blur bb-login-hero-blur-y" />
          <div className="bb-login-hero-shade" />
        </div>
        <p className="bb-login-hero-topbar">{copy.topBar}</p>
        <div className="bb-login-hero-content">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="bb-login-hero-logo" src="/brand/brobond-logo.png" alt="Brobond" />
          <span className="bb-login-hero-eyebrow">{copy.eyebrow}</span>
          <h1 className="bb-login-hero-title">{copy.title}</h1>
          <p className="bb-login-hero-subtitle">{copy.subtitle}</p>
        </div>
      </div>
      <div className="bb-login-hero-features">
        <LoginFeatures copy={copy} />
      </div>
    </aside>
  );
}

export default LoginHeroPanel;
