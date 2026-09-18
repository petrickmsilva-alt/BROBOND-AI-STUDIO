'use client';

/**
 * PR009.6 — the five studio pillars on the login hero (Diretor IA,
 * Storyboard, Imagem & Vídeo, Assets, Quality). One markup, two layouts: a
 * 5-column grid on wide screens and a snap carousel everywhere else — pure
 * CSS, the component itself never branches.
 */
import { BadgeCheck, Clapperboard, Film, Layers3, Library } from 'lucide-react';
import type { LoginCopy } from './login-copy';

const FEATURE_ICONS = [Clapperboard, Layers3, Film, Library, BadgeCheck];

export function LoginFeatures({ copy }: { copy: LoginCopy }) {
  return (
    <ul className="bb-login-features" role="list">
      {copy.features.map((feature, index) => {
        const Icon = FEATURE_ICONS[index] ?? BadgeCheck;
        return (
          <li key={feature.title} className="bb-login-feature">
            <span className="bb-login-feature-icon">
              <Icon size={17} strokeWidth={1.9} aria-hidden="true" />
            </span>
            <strong>{feature.title}</strong>
            <small>{feature.subtitle}</small>
          </li>
        );
      })}
    </ul>
  );
}

export default LoginFeatures;
