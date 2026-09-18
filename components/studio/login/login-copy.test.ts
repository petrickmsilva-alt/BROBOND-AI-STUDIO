// PR009.6 — login copy contract: PT and EN ship in lockstep, the five hero
// features keep their order, and the exact brand strings (título, botões,
// rodapé) stay verbatim. Pure data — no jsdom needed.

import { describe, expect, it } from 'vitest';
import { LOGIN_COPY, type LoginCopy } from './login-copy';

const PT_KEYS = Object.keys(LOGIN_COPY.pt) as Array<keyof LoginCopy>;

describe('PR009.6 login copy (PT/EN lockstep)', () => {
  it('ships exactly pt and en', () => {
    expect(Object.keys(LOGIN_COPY).sort()).toEqual(['en', 'pt']);
  });

  it('keeps every key present in both languages', () => {
    expect(Object.keys(LOGIN_COPY.en)).toEqual(Object.keys(LOGIN_COPY.pt));
    for (const key of PT_KEYS) {
      expect(LOGIN_COPY.en[key], `en.${key}`).toBeDefined();
      expect(LOGIN_COPY.pt[key], `pt.${key}`).toBeDefined();
    }
  });

  it('lists the five hero features, in order, in both languages', () => {
    expect(LOGIN_COPY.pt.features.map(feature => feature.title)).toEqual([
      'Diretor IA',
      'Storyboard',
      'Imagem & Vídeo',
      'Assets',
      'Quality',
    ]);
    expect(LOGIN_COPY.en.features.map(feature => feature.title)).toEqual([
      'AI Director',
      'Storyboard',
      'Image & Video',
      'Assets',
      'Quality',
    ]);
    for (const language of ['pt', 'en'] as const) {
      for (const feature of LOGIN_COPY[language].features) {
        expect(feature.subtitle.length).toBeGreaterThan(0);
      }
    }
  });

  it('carries the exact brand strings', () => {
    expect(LOGIN_COPY.pt.topBar).toBe('IA • CINEMA • MARCA • IMPACTO');
    expect(LOGIN_COPY.pt.eyebrow).toBe('BROBOND WEAR');
    expect(LOGIN_COPY.pt.title).toBe('Transforme ideias em grandes campanhas.');
    expect(LOGIN_COPY.pt.cardTitle).toBe('Bem-vindo de volta');
    expect(LOGIN_COPY.pt.cardSubtitle).toBe('Entre no seu estúdio e continue criando o extraordinário.');
    expect(LOGIN_COPY.pt.signIn).toBe('Entrar no Brobond Studio');
    expect(LOGIN_COPY.pt.google).toBe('Entrar com Google');
    expect(LOGIN_COPY.pt.version).toBe('Brobond Studio v4.0.1');
    expect(LOGIN_COPY.pt.online).toBe('Sistema Online');
  });
});
