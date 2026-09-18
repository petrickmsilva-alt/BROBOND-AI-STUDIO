'use client';

/**
 * PR009.6.1 — Pixel Perfect Login: the five studio pillars in the hero
 * footer (Diretor IA, Storyboard, Imagem & Vídeo, Assets, Quality).
 *
 * Five identical cards, horizontally aligned on one row: 110×88, glass at
 * rgba(10,10,10,.38) with a 16px blur and a 10% gold border, a gold icon,
 * a white title and a grey caption. They live in their own grid row of the
 * hero column, so they can never overlap the copy above them.
 */
import { Film, FolderOpen, Image as ImageIcon, ListChecks, ShieldCheck } from 'lucide-react';
import type { LoginCopy } from './login-copy';

const FEATURE_ICONS = [Film, ListChecks, ImageIcon, FolderOpen, ShieldCheck];

export function LoginFeatures({ copy }: { copy: LoginCopy }) {
  return (
    <ul className="bb-login-features" role="list">
      {copy.features.map((feature, index) => {
        const Icon = FEATURE_ICONS[index] ?? ShieldCheck;
        return (
          <li key={feature.title} className="bb-login-feature">
            <Icon className="bb-login-feature-icon" size={22} strokeWidth={1.6} aria-hidden="true" />
            <strong>{feature.title}</strong>
            <small>{feature.subtitle}</small>
          </li>
        );
      })}
    </ul>
  );
}

export default LoginFeatures;
