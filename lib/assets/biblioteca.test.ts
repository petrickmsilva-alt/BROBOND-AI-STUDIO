/**
 * PR009.7 — Biblioteca Criativa: o domínio puro.
 *
 * Categorias, tags, badge de qualidade, busca instantânea, ordenação e os
 * formatadores pt-BR. O contrato de honestidade é fixado aqui: desconhecido
 * vira `—`, nunca um zero, uma unidade chutada ou um rótulo inventado.
 */
import { describe, expect, it } from 'vitest';

import {
  BIBLIOTECA_COPY,
  CATEGORIES,
  DEFAULT_VIEW,
  KIND_BADGE,
  SORT_OPTIONS,
  UNKNOWN,
  applyView,
  assetKind,
  countCategories,
  displayTags,
  formatClock,
  formatDateBR,
  formatSizeBR,
  matchesCategory,
  matchesSearch,
  normalizeText,
  qualityBadge,
  resolutionBR,
  sortLibrary,
  type LibraryAsset,
} from './biblioteca';

let seq = 0;

function asset(overrides: Partial<LibraryAsset> = {}): LibraryAsset {
  seq += 1;
  return {
    id: `a-${seq}`,
    name: `Arquivo ${seq}.png`,
    kind: 'image',
    url: `/files/a-${seq}.png`,
    created_at: '2026-08-12T11:22:33Z',
    has_metadata: true,
    ...overrides,
  };
}

const NO_FAVORITES: ReadonlySet<string> = new Set<string>();

describe('nomenclatura (REGRA 1)', () => {
  it('fala Biblioteca em toda a interface', () => {
    expect(BIBLIOTECA_COPY.navLabel).toBe('Biblioteca');
    expect(BIBLIOTECA_COPY.title).toBe('Biblioteca Criativa');
    expect(BIBLIOTECA_COPY.subtitle).toBe('Gerencie imagens, vídeos e arquivos da Brobond.');
    expect(BIBLIOTECA_COPY.breadcrumb).toBe('Workspace / Biblioteca');
    expect(BIBLIOTECA_COPY.openLibrary).toBe('Abrir Biblioteca');
    expect(BIBLIOTECA_COPY.dropHint).toBe('Arraste imagens e vídeos aqui');
    // Nenhuma string visível carrega a palavra "Asset".
    Object.values(BIBLIOTECA_COPY).forEach(value => {
      expect(value.toLowerCase()).not.toContain('asset');
    });
  });
});

describe('tipos e badges', () => {
  it('normaliza o kind armazenado', () => {
    expect(assetKind(asset({ kind: 'image' }))).toBe('image');
    expect(assetKind(asset({ kind: 'VIDEO' }))).toBe('video');
    expect(assetKind(asset({ kind: 'audio' }))).toBe('audio');
  });

  it('cai no content_type quando o kind é desconhecido', () => {
    expect(assetKind(asset({ kind: 'blob', content_type: 'video/mp4' }))).toBe('video');
    expect(assetKind(asset({ kind: 'blob', content_type: 'image/png' }))).toBe('image');
    expect(assetKind(asset({ kind: 'blob', content_type: 'audio/mpeg' }))).toBe('audio');
    expect(assetKind(asset({ kind: 'blob', content_type: 'application/pdf' }))).toBe('other');
    expect(assetKind(asset({ kind: '', content_type: null }))).toBe('other');
    // Uma linha antiga sem kind nenhum também é honestamente "other".
    expect(assetKind({ kind: null as unknown as string, content_type: undefined })).toBe('other');
  });

  it('imprime IMG · VIDEO · AUDIO', () => {
    expect(KIND_BADGE.image).toBe('IMG');
    expect(KIND_BADGE.video).toBe('VIDEO');
    expect(KIND_BADGE.audio).toBe('AUDIO');
    expect(KIND_BADGE.other).toBe('FILE');
  });
});

describe('categorias', () => {
  it('oferece exatamente as nove do briefing, na ordem', () => {
    expect(CATEGORIES.map(item => item.label)).toEqual([
      'Todos',
      'Imagens',
      'Vídeos',
      'Áudios',
      'Favoritos',
      'Aprovados',
      'Campanhas',
      'Bastidores',
      'Produtos',
    ]);
  });

  it('classifica por tipo, favorito e aprovação', () => {
    const image = asset({ kind: 'image' });
    const video = asset({ kind: 'video' });
    const audio = asset({ kind: 'audio' });
    const approved = asset({ quality_status: 'approved' });
    const favorites = new Set([video.id]);

    expect(matchesCategory(image, 'todos', NO_FAVORITES)).toBe(true);
    expect(matchesCategory(image, 'imagens', NO_FAVORITES)).toBe(true);
    expect(matchesCategory(image, 'videos', NO_FAVORITES)).toBe(false);
    expect(matchesCategory(video, 'videos', NO_FAVORITES)).toBe(true);
    expect(matchesCategory(audio, 'audios', NO_FAVORITES)).toBe(true);
    expect(matchesCategory(video, 'favoritos', favorites)).toBe(true);
    expect(matchesCategory(image, 'favoritos', favorites)).toBe(false);
    expect(matchesCategory(approved, 'aprovados', NO_FAVORITES)).toBe(true);
  });

  it('usa as palavras já gravadas nos metadados para as categorias temáticas', () => {
    expect(matchesCategory(asset({ tags: ['CAMPANHA'] }), 'campanhas', NO_FAVORITES)).toBe(true);
    expect(matchesCategory(asset({ project: 'Bastidores RAM' }), 'bastidores', NO_FAVORITES)).toBe(true);
    expect(matchesCategory(asset({ name: 'packshot-01.png' }), 'produtos', NO_FAVORITES)).toBe(true);
    // Sem metadado não há palpite: o arquivo simplesmente não entra.
    expect(matchesCategory(asset({ name: 'sem-nada.png' }), 'campanhas', NO_FAVORITES)).toBe(false);
  });

  it('conta cada categoria', () => {
    const items = [
      asset({ kind: 'image', quality_status: 'approved' }),
      asset({ kind: 'video', tags: ['Campanha'] }),
      asset({ kind: 'audio' }),
    ];
    const counts = countCategories(items, new Set([items[2].id]));
    expect(counts.todos).toBe(3);
    expect(counts.imagens).toBe(1);
    expect(counts.videos).toBe(1);
    expect(counts.audios).toBe(1);
    expect(counts.favoritos).toBe(1);
    expect(counts.aprovados).toBe(1);
    expect(counts.campanhas).toBe(1);
    expect(counts.bastidores).toBe(0);
    expect(counts.produtos).toBe(0);
  });
});

describe('qualidade', () => {
  it('prefere o quality_status existente', () => {
    expect(qualityBadge({ quality_status: 'approved', quality_score: 10 }).id).toBe('aprovado');
    expect(qualityBadge({ quality_status: 'aprovado', quality_score: null }).label).toBe('Aprovado');
    expect(qualityBadge({ quality_status: 'masterpiece', quality_score: null }).id).toBe('aprovado');
    expect(qualityBadge({ quality_status: 'review', quality_score: null }).id).toBe('revisao');
    expect(qualityBadge({ quality_status: 'em revisão', quality_score: null }).label).toBe('Em revisão');
    expect(qualityBadge({ quality_status: 'pending', quality_score: null }).id).toBe('revisao');
    expect(qualityBadge({ quality_status: 'retry', quality_score: null }).id).toBe('rascunho');
  });

  it('cai nas faixas do score quando não há status', () => {
    expect(qualityBadge({ quality_status: null, quality_score: 95 }).id).toBe('aprovado');
    expect(qualityBadge({ quality_status: null, quality_score: 85 }).id).toBe('aprovado');
    expect(qualityBadge({ quality_status: null, quality_score: 70 }).id).toBe('revisao');
    expect(qualityBadge({ quality_status: '', quality_score: 40 }).id).toBe('rascunho');
  });

  it('sem nada conhecido é rascunho, nunca uma aprovação inventada', () => {
    expect(qualityBadge({ quality_status: null, quality_score: null }).id).toBe('rascunho');
  });
});

describe('tags visuais', () => {
  it('usa as tags, o projeto e a persona já gravados, em maiúsculas e sem repetir', () => {
    const tags = displayTags(asset({ tags: ['brobond', 'verão'], project: 'Brobond', persona: 'Ayla' }));
    expect(tags).toEqual(['BROBOND', 'VERÃO', 'AYLA']);
  });

  it('respeita o limite e devolve vazio quando não há metadado', () => {
    expect(displayTags(asset({ tags: ['a', 'b', 'c', 'd'] }), 2)).toEqual(['A', 'B']);
    expect(displayTags(asset({ tags: [], project: null, persona: '  ' }))).toEqual([]);
    expect(displayTags(asset({ tags: undefined, project: undefined, persona: undefined }))).toEqual([]);
  });
});

describe('busca instantânea', () => {
  const item = asset({ name: 'Lookbook Verão.png', kind: 'image', tags: ['RAM2026'], project: 'Brobond' });

  it('procura por nome, tipo e tag — ignorando acento e caixa', () => {
    expect(matchesSearch(item, 'lookbook')).toBe(true);
    expect(matchesSearch(item, 'VERAO')).toBe(true);
    expect(matchesSearch(item, 'ram2026')).toBe(true);
    expect(matchesSearch(item, 'img')).toBe(true);
    expect(matchesSearch(item, 'image')).toBe(true);
    expect(matchesSearch(item, 'brobond')).toBe(true);
    expect(matchesSearch(item, 'inexistente')).toBe(false);
  });

  it('uma busca vazia não corta nada', () => {
    expect(matchesSearch(item, '   ')).toBe(true);
  });

  it('procura também no content_type e no source, sem exigir nenhum deles', () => {
    expect(matchesSearch(asset({ content_type: 'video/mp4', kind: 'video' }), 'mp4')).toBe(true);
    expect(matchesSearch(asset({ source: 'render-queue', content_type: null }), 'render')).toBe(true);
  });

  it('normaliza texto para comparação', () => {
    expect(normalizeText('  Áudio Único ')).toBe('audio unico');
  });
});

describe('ordenação', () => {
  const older = asset({ name: 'Zebra.png', created_at: '2026-01-01T00:00:00Z', size_bytes: 10 });
  const newer = asset({ name: 'Alfa.png', created_at: '2026-09-01T00:00:00Z', size_bytes: 900 });
  const items = [older, newer];

  it('oferece as cinco ordens do briefing', () => {
    expect(SORT_OPTIONS.map(option => option.label)).toEqual([
      'Mais recente',
      'Mais antigo',
      'Nome A-Z',
      'Nome Z-A',
      'Maior arquivo',
    ]);
  });

  it('ordena sem mutar a entrada', () => {
    expect(sortLibrary(items, 'recentes')[0].id).toBe(newer.id);
    expect(sortLibrary(items, 'antigos')[0].id).toBe(older.id);
    expect(sortLibrary(items, 'nome-az')[0].id).toBe(newer.id);
    expect(sortLibrary(items, 'nome-za')[0].id).toBe(older.id);
    expect(sortLibrary(items, 'maiores')[0].id).toBe(newer.id);
    expect(items[0].id).toBe(older.id);
  });

  it('trata data inválida e tamanho ausente como o fundo da lista', () => {
    const broken = asset({ created_at: 'nao-e-data', size_bytes: null });
    expect(sortLibrary([broken, newer], 'recentes')[0].id).toBe(newer.id);
    expect(sortLibrary([broken, newer], 'maiores')[0].id).toBe(newer.id);
  });
});

describe('applyView', () => {
  it('aplica categoria, busca e ordenação em uma passada', () => {
    const a = asset({ kind: 'image', name: 'Beta.png', created_at: '2026-02-01T00:00:00Z' });
    const b = asset({ kind: 'image', name: 'Alfa.png', created_at: '2026-03-01T00:00:00Z' });
    const c = asset({ kind: 'video', name: 'Alfa.mp4', created_at: '2026-04-01T00:00:00Z' });
    const view = { category: 'imagens' as const, search: 'alfa', sort: 'nome-az' as const };
    expect(applyView([a, b, c], view, NO_FAVORITES).map(item => item.id)).toEqual([b.id]);
  });

  it('parte de Todos, sem busca, pelos mais recentes', () => {
    expect(DEFAULT_VIEW).toEqual({ category: 'todos', search: '', sort: 'recentes' });
  });
});

describe('formatadores pt-BR (honestos)', () => {
  it('data em dd/mm/aaaa, ou — quando não dá para saber', () => {
    expect(formatDateBR('2026-08-12T11:22:33Z')).toBe('12/08/2026');
    expect(formatDateBR(null)).toBe(UNKNOWN);
    expect(formatDateBR('')).toBe(UNKNOWN);
    expect(formatDateBR('nao-e-data')).toBe(UNKNOWN);
  });

  it('tamanho com vírgula decimal, ou —', () => {
    expect(formatSizeBR(512)).toBe('512 B');
    expect(formatSizeBR(2048)).toBe('2,0 KB');
    expect(formatSizeBR(5 * 1024 * 1024)).toBe('5,0 MB');
    expect(formatSizeBR(300 * 1024)).toBe('300 KB');
    expect(formatSizeBR(3 * 1024 * 1024 * 1024)).toBe('3,0 GB');
    expect(formatSizeBR(null)).toBe(UNKNOWN);
    expect(formatSizeBR(-1)).toBe(UNKNOWN);
    expect(formatSizeBR(Number.NaN)).toBe(UNKNOWN);
  });

  it('resolução: a string armazenada, depois width×height, depois —', () => {
    expect(resolutionBR({ resolution: '1920×1080', width: null, height: null })).toBe('1920×1080');
    expect(resolutionBR({ resolution: null, width: 800, height: 600 })).toBe('800×600');
    expect(resolutionBR({ resolution: null, width: null, height: null })).toBe(UNKNOWN);
  });

  it('relógio mm:ss, ou —', () => {
    expect(formatClock(0)).toBe('00:00');
    expect(formatClock(75.6)).toBe('01:15');
    expect(formatClock(null)).toBe(UNKNOWN);
    expect(formatClock(-3)).toBe(UNKNOWN);
    expect(formatClock(Number.POSITIVE_INFINITY)).toBe(UNKNOWN);
  });
});
