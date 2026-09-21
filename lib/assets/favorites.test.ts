// @vitest-environment jsdom
/**
 * PR009.7 — favoritos locais: a estrela salva no dispositivo, nunca no
 * backend. O seam é um cookie nomeado (o mesmo precedente de
 * `lib/memory/remembered_login.ts`), então nenhum endpoint é chamado.
 */
import { beforeEach, describe, expect, it } from 'vitest';

import { FAVORITES_DAYS, loadFavorites, saveFavorites, toggleFavorite } from './favorites';

function clearJar() {
  document.cookie.split('; ').forEach(entry => {
    const name = entry.split('=')[0];
    if (name) document.cookie = `${name}=; Max-Age=0; Path=/`;
  });
}

beforeEach(clearJar);

describe('favoritos', () => {
  it('começa vazio quando não há nada gravado', () => {
    expect(loadFavorites().size).toBe(0);
  });

  it('grava e relê os ids marcados', () => {
    saveFavorites(new Set(['asset-1', 'asset-2']));
    const loaded = loadFavorites();
    expect(loaded.has('asset-1')).toBe(true);
    expect(loaded.has('asset-2')).toBe(true);
    expect(loaded.size).toBe(2);
  });

  it('sobrevive a ids com caracteres especiais', () => {
    saveFavorites(new Set(['a,b', 'c=d e']));
    const loaded = loadFavorites();
    expect(loaded.has('a,b')).toBe(true);
    expect(loaded.has('c=d e')).toBe(true);
  });

  it('um conjunto vazio limpa a marcação', () => {
    saveFavorites(new Set(['asset-1']));
    saveFavorites(new Set());
    expect(loadFavorites().size).toBe(0);
  });

  it('toggle é puro: devolve um novo conjunto', () => {
    const start: ReadonlySet<string> = new Set(['a']);
    const added = toggleFavorite(start, 'b');
    expect(Array.from(added).sort()).toEqual(['a', 'b']);
    expect(start.size).toBe(1);
    const removed = toggleFavorite(added, 'a');
    expect(Array.from(removed)).toEqual(['b']);
  });

  it('a preferência dura um ano', () => {
    expect(FAVORITES_DAYS).toBe(365);
  });

  it('ignora um jar com outros cookies e um valor vazio', () => {
    document.cookie = 'outro=1; Path=/';
    expect(loadFavorites().size).toBe(0);
    document.cookie = 'brobond_biblioteca_favoritos=; Path=/';
    expect(loadFavorites().size).toBe(0);
  });

  it('descarta um id impossível de codificar em vez de quebrar', () => {
    // Um surrogate solto faz encodeURIComponent lançar: o id some, o resto fica.
    saveFavorites(new Set(['\uD800', 'valido']));
    expect(Array.from(loadFavorites())).toEqual(['valido']);
  });

  it('descarta entradas mal codificadas em vez de quebrar', () => {
    document.cookie = 'brobond_biblioteca_favoritos=%E0%A4%A,ok; Path=/';
    expect(Array.from(loadFavorites())).toEqual(['ok']);
  });

  it('um cookie bloqueado nunca quebra a Biblioteca', () => {
    const jar = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie');
    Object.defineProperty(document, 'cookie', {
      configurable: true,
      get() {
        throw new Error('bloqueado');
      },
      set() {
        throw new Error('bloqueado');
      },
    });
    try {
      expect(loadFavorites().size).toBe(0);
      expect(() => saveFavorites(new Set(['a']))).not.toThrow();
    } finally {
      if (jar) Object.defineProperty(document, 'cookie', jar);
      else delete (document as unknown as Record<string, unknown>).cookie;
    }
  });

  it('fora do navegador (SSR) a marcação é simplesmente vazia', async () => {
    const original = globalThis.document;
    // @ts-expect-error — simulando o servidor: não há document.
    delete globalThis.document;
    try {
      const module = await import('./favorites?ssr');
      expect(module.loadFavorites().size).toBe(0);
      expect(() => module.saveFavorites(new Set(['a']))).not.toThrow();
    } finally {
      globalThis.document = original;
    }
  });
});
