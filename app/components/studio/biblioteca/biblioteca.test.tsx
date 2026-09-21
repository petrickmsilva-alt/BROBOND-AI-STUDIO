// @vitest-environment jsdom
/**
 * PR009.7 — Biblioteca Criativa: o contrato do módulo, ponta a ponta.
 *
 * `lib/api` é a única fronteira mockada (a rede em si está coberta em
 * `lib/network/upload.test.ts`). Todo o resto — header, rail de categorias,
 * grid, card, preview, drag & drop, busca e ordenação — é o módulo de
 * produção, então esta suíte se lê como a Definition of Done.
 */
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { LibraryAsset } from '../../../../lib/assets/biblioteca';

vi.mock('../../../../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../../../../lib/api')>('../../../../lib/api');
  return { ...actual, listAssetLibrary: vi.fn(), uploadLibraryAsset: vi.fn() };
});

import { NetworkErrorType, listAssetLibrary, uploadLibraryAsset } from '../../../../lib/api';
import type { UploadProgress } from '../../../../lib/api';
import { Biblioteca } from './biblioteca';

const listMock = vi.mocked(listAssetLibrary);
const uploadMock = vi.mocked(uploadLibraryAsset);

let sequence = 0;

function asset(overrides: Partial<LibraryAsset> = {}): LibraryAsset {
  sequence += 1;
  return {
    id: `lib-${sequence}`,
    name: `Cena ${sequence}.png`,
    kind: 'image',
    url: `/files/cena-${sequence}.png`,
    created_at: `2026-08-${String(10 + sequence).padStart(2, '0')}T11:22:33Z`,
    has_metadata: true,
    project: 'Brobond',
    persona: 'Ayla',
    provider: 'flux',
    seed: 1000 + sequence,
    width: 1920,
    height: 1080,
    resolution: '1920×1080',
    size_bytes: 1024 * 1024,
    tags: ['LOOKBOOK'],
    quality_score: 90,
    quality_status: 'approved',
    thumbnail_url: `/files/thumbs/cena-${sequence}.jpg`,
    ...overrides,
  };
}

function pngFile(name = 'quadro.png', size = 100_000) {
  return new File([new Uint8Array(size)], name, { type: 'image/png' });
}

function drop(files: File[]) {
  const zone = screen.getByTestId('bib-dropzone');
  fireEvent.dragEnter(zone, { dataTransfer: { files, types: ['Files'], dropEffect: '' } });
  fireEvent.drop(zone, { dataTransfer: { files, types: ['Files'], dropEffect: '' } });
}

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void };

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(resolver => {
    resolve = resolver;
  });
  return { promise, resolve };
}

function ok<T>(data: T) {
  return { data, remote: true, status: 200 } as never;
}

function fail(error: string, errorType?: NetworkErrorType) {
  return { data: [], remote: false, error, errorType } as never;
}

async function renderReady(items: LibraryAsset[]) {
  listMock.mockResolvedValue(ok(items));
  render(<Biblioteca />);
  await screen.findByTestId('bib-root');
  if (items.length) await screen.findByTestId('bib-grid');
}

beforeEach(() => {
  listMock.mockReset();
  uploadMock.mockReset();
  document.cookie.split('; ').forEach(entry => {
    const name = entry.split('=')[0];
    if (name) document.cookie = `${name}=; Max-Age=0; Path=/`;
  });
});

describe('nomenclatura na interface', () => {
  it('chama tudo de Biblioteca — a palavra "Assets" não aparece', async () => {
    await renderReady([asset()]);
    expect(screen.getByRole('heading', { name: /Biblioteca Criativa/ })).toBeInTheDocument();
    expect(screen.getByText('Gerencie imagens, vídeos e arquivos da Brobond.')).toBeInTheDocument();
    const crumb = screen.getByLabelText('Trilha');
    expect(within(crumb).getByText('Workspace')).toBeInTheDocument();
    expect(within(crumb).getByText('Biblioteca')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\bassets?\b/i);
  });

  it('mantém o header de 72px com pesquisa, filtro, ordenação e upload dourado', async () => {
    await renderReady([asset()]);
    expect(screen.getByLabelText('Pesquisar na Biblioteca')).toBeInTheDocument();
    expect(screen.getByLabelText('Filtrar categoria')).toBeInTheDocument();
    expect(screen.getByLabelText('Ordenar Biblioteca')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Upload/ })).toBeInTheDocument();
  });
});

describe('leitura e estados', () => {
  it('mostra uma linha calma antes de qualquer resposta', async () => {
    listMock.mockReturnValue(new Promise(() => undefined) as never);
    render(<Biblioteca />);
    expect(await screen.findByText('Lendo a Biblioteca…')).toBeInTheDocument();
  });

  it('renderiza a Biblioteca real e conta cada categoria', async () => {
    const counted = vi.fn();
    listMock.mockResolvedValue(ok([asset({ kind: 'image' }), asset({ kind: 'video' })]));
    render(<Biblioteca onCounted={counted} />);
    await screen.findByTestId('bib-grid');
    expect(screen.getByTestId('bib-count-todos')).toHaveTextContent('2');
    expect(screen.getByTestId('bib-count-imagens')).toHaveTextContent('1');
    expect(screen.getByTestId('bib-count-videos')).toHaveTextContent('1');
    expect(counted).toHaveBeenCalledWith({ all: 2, image: 1, video: 1 });
  });

  it('API inalcançável vira "sem conexão", e tenta de novo sob demanda', async () => {
    listMock.mockResolvedValueOnce(fail('sem resposta', NetworkErrorType.OFFLINE));
    render(<Biblioteca />);
    await screen.findByTestId('bib-state-offline');
    listMock.mockResolvedValueOnce(ok([asset()]));
    fireEvent.click(screen.getByRole('button', { name: /Tentar novamente/ }));
    await screen.findByTestId('bib-grid');
  });

  it('CORS e timeout de cold start também são "sem conexão"', async () => {
    listMock.mockResolvedValueOnce(fail('cors', NetworkErrorType.CORS));
    const view = render(<Biblioteca />);
    await screen.findByTestId('bib-state-offline');
    view.unmount();
    listMock.mockResolvedValueOnce(fail('timeout', NetworkErrorType.TIMEOUT));
    render(<Biblioteca />);
    await screen.findByTestId('bib-state-offline');
  });

  it('um erro da API aparece com as palavras do servidor', async () => {
    listMock.mockResolvedValueOnce(fail('500 internal', NetworkErrorType.SERVER));
    render(<Biblioteca />);
    await screen.findByTestId('bib-state-erro');
    expect(screen.getByText('500 internal')).toBeInTheDocument();
  });

  it('a Biblioteca vazia convida ao arrasto', async () => {
    await renderReady([]);
    expect(await screen.findByTestId('bib-state-vazia')).toBeInTheDocument();
  });
});

describe('busca, filtro e ordenação', () => {
  it('a busca corta o grid a cada tecla e assume o recorte vazio', async () => {
    await renderReady([asset({ name: 'Lookbook Verão.png' }), asset({ name: 'Bastidores.png' })]);
    const search = screen.getByLabelText('Pesquisar na Biblioteca');
    fireEvent.change(search, { target: { value: 'verao' } });
    expect(screen.getByTestId('bib-grid').children).toHaveLength(1);
    fireEvent.change(search, { target: { value: 'nada disso' } });
    expect(screen.getByTestId('bib-state-filtrada')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Limpar recorte/ }));
    expect(screen.getByTestId('bib-grid').children).toHaveLength(2);
  });

  it('o rail de categorias corta por tipo', async () => {
    await renderReady([asset({ kind: 'image' }), asset({ kind: 'video' })]);
    fireEvent.click(within(screen.getByTestId('bib-rail')).getByRole('button', { name: /Vídeos/ }));
    expect(screen.getByTestId('bib-grid').children).toHaveLength(1);
    fireEvent.click(within(screen.getByTestId('bib-rail')).getByRole('button', { name: /Todos/ }));
    expect(screen.getByTestId('bib-grid').children).toHaveLength(2);
  });

  it('a ordenação reordena o grid', async () => {
    const first = asset({ name: 'Alfa.png', created_at: '2026-01-01T00:00:00Z' });
    const second = asset({ name: 'Zulu.png', created_at: '2026-05-01T00:00:00Z' });
    await renderReady([first, second]);
    expect(screen.getByTestId('bib-grid').children[0]).toHaveAttribute('data-testid', `bib-card-${second.id}`);
    fireEvent.click(screen.getByLabelText('Ordenar Biblioteca'));
    fireEvent.click(screen.getByRole('option', { name: 'Nome A-Z' }));
    expect(screen.getByTestId('bib-grid').children[0]).toHaveAttribute('data-testid', `bib-card-${first.id}`);
  });

  it('o filtro do header troca a categoria', async () => {
    await renderReady([asset({ kind: 'image' }), asset({ kind: 'video' })]);
    fireEvent.click(screen.getByLabelText('Filtrar categoria'));
    fireEvent.click(screen.getByRole('option', { name: 'Imagens' }));
    expect(screen.getByTestId('bib-grid').children).toHaveLength(1);
  });
});

describe('upload — arrastar e soltar', () => {
  it('envia um PNG solto com progresso real e o prepende concluído, sem refresh', async () => {
    await renderReady([]);
    const pending = deferred<unknown>();
    let report: ((progress: UploadProgress) => void) | undefined;
    uploadMock.mockImplementation((_file, options) => {
      report = options?.onProgress;
      return pending.promise as never;
    });

    drop([pngFile()]);
    await screen.findByTestId('bib-upload-uploading');
    act(() => report?.({ loaded: 50_000, total: 100_000, bytesPerSecond: 25_000 }));
    expect(screen.getByLabelText('progresso')).toHaveTextContent('50%');

    const created = asset({ name: 'quadro.png' });
    await act(async () => {
      pending.resolve({ data: created, remote: true, status: 201 });
      await pending.promise;
    });

    expect(await screen.findByTestId('bib-upload-completed')).toBeInTheDocument();
    // A listagem NÃO é relida: o 201 já atualiza a Biblioteca.
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId(`bib-card-${created.id}`)).toBeInTheDocument();
  });

  it('uma falha continua falha, com o texto do servidor ao lado', async () => {
    await renderReady([]);
    uploadMock.mockResolvedValue({ data: null, remote: false, error: 'arquivo grande demais' } as never);
    drop([pngFile()]);
    expect(await screen.findByTestId('bib-upload-failed')).toBeInTheDocument();
    expect(screen.getByText('arquivo grande demais')).toBeInTheDocument();
  });

  it('sem texto de erro a mensagem é honesta, não inventada', async () => {
    await renderReady([]);
    uploadMock.mockResolvedValue({ data: null, remote: false } as never);
    drop([pngFile()]);
    expect(await screen.findByText('Falha no upload')).toBeInTheDocument();
  });

  it('recusa tipos fora da lista, dizendo quais', async () => {
    await renderReady([]);
    drop([new File(['x'], 'planilha.xlsx', { type: 'application/vnd.ms-excel' })]);
    expect(await screen.findByTestId('bib-notice')).toHaveTextContent('planilha.xlsx');
    expect(uploadMock).not.toHaveBeenCalled();
  });

  it('mostra o overlay pontilhado enquanto os arquivos pairam', async () => {
    await renderReady([asset()]);
    const zone = screen.getByTestId('bib-dropzone');
    fireEvent.dragEnter(zone, { dataTransfer: { files: [], types: ['Files'], dropEffect: '' } });
    expect(screen.getByTestId('bib-drop-overlay')).toBeInTheDocument();
    expect(screen.getAllByText('Arraste imagens e vídeos aqui').length).toBeGreaterThan(0);
    fireEvent.dragLeave(zone, { dataTransfer: { files: [], types: ['Files'], dropEffect: '' } });
    expect(screen.queryByTestId('bib-drop-overlay')).toBeNull();
  });

  it('entrega a fila ao pai por registerEnqueue', async () => {
    listMock.mockResolvedValue(ok([]));
    let enqueue: (files: File[]) => void = () => undefined;
    render(<Biblioteca registerEnqueue={handler => { enqueue = handler; }} />);
    await screen.findByTestId('bib-state-vazia');
    uploadMock.mockResolvedValue({ data: asset(), remote: true, status: 201 } as never);
    await act(async () => {
      enqueue([pngFile()]);
    });
    expect(uploadMock).toHaveBeenCalledTimes(1);
  });
});

describe('preview', () => {
  it('abre em modal a partir do card e fecha de volta no grid', async () => {
    const item = asset();
    await renderReady([item]);
    fireEvent.click(screen.getByLabelText(`Abrir ${item.name}`));
    expect(await screen.findByTestId('bib-modal')).toBeInTheDocument();
    expect(screen.getByTestId('bib-preview-image')).toBeInTheDocument();
    fireEvent.click(screen.getAllByLabelText('Fechar preview')[0]);
    expect(screen.queryByTestId('bib-modal')).toBeNull();
  });

  it('a imagem tem zoom, download e informações', async () => {
    const item = asset();
    await renderReady([item]);
    fireEvent.click(screen.getByLabelText(`Abrir ${item.name}`));
    await screen.findByTestId('bib-modal');
    expect(screen.getByLabelText('nível de zoom')).toHaveTextContent('100%');
    fireEvent.click(screen.getByLabelText('Aumentar zoom'));
    expect(screen.getByLabelText('nível de zoom')).toHaveTextContent('150%');
    fireEvent.click(screen.getByLabelText('Reduzir zoom'));
    expect(screen.getByLabelText('nível de zoom')).toHaveTextContent('100%');
    expect(screen.getByRole('link', { name: /Download/ })).toHaveAttribute('href', item.url);
    expect(screen.getByLabelText('Informações do arquivo')).toBeInTheDocument();
  });

  it('o vídeo abre com player, timeline, volume e tela cheia', async () => {
    const item = asset({ kind: 'video', name: 'Take 01.mp4', url: '/files/take.mp4' });
    await renderReady([item]);
    fireEvent.click(screen.getByLabelText(`Abrir ${item.name}`));
    await screen.findByTestId('bib-stage-video');
    expect(screen.getByLabelText('Linha do tempo')).toBeInTheDocument();
    expect(screen.getByLabelText('Volume')).toBeInTheDocument();
    expect(screen.getByLabelText('Tela cheia')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Silenciar'));
    expect(screen.getByLabelText('Ativar som')).toBeInTheDocument();
  });

  it('Escape fecha o preview', async () => {
    const item = asset();
    await renderReady([item]);
    fireEvent.click(screen.getByLabelText(`Abrir ${item.name}`));
    await screen.findByTestId('bib-modal');
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByTestId('bib-modal')).toBeNull();
  });
});

describe('favoritos', () => {
  it('a estrela marca localmente e alimenta a categoria Favoritos', async () => {
    const item = asset();
    await renderReady([item]);
    expect(screen.getByTestId('bib-count-favoritos')).toHaveTextContent('0');
    fireEvent.click(screen.getByLabelText(`Favoritar ${item.name}`));
    expect(screen.getByTestId('bib-count-favoritos')).toHaveTextContent('1');
    expect(document.cookie).toContain('brobond_biblioteca_favoritos');
    fireEvent.click(screen.getByLabelText(`Remover ${item.name} dos favoritos`));
    expect(screen.getByTestId('bib-count-favoritos')).toHaveTextContent('0');
  });
});

describe('menu do card', () => {
  it('copia a URL do arquivo sem chamar endpoint novo', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    const item = asset();
    await renderReady([item]);
    fireEvent.click(screen.getByLabelText(`Mais opções para ${item.name}`));
    fireEvent.click(screen.getByRole('menuitem', { name: /Copiar URL/ }));
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}${item.url}`);
    expect(await screen.findByText('URL copiada.')).toBeInTheDocument();
  });

  it('sem área de transferência mostra a URL em vez de mentir sobre a cópia', async () => {
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
    const item = asset();
    await renderReady([item]);
    fireEvent.click(screen.getByLabelText(`Mais opções para ${item.name}`));
    fireEvent.click(screen.getByRole('menuitem', { name: /Copiar URL/ }));
    expect(await screen.findByText(`${window.location.origin}${item.url}`)).toBeInTheDocument();
  });

  it('uma URL absoluta é copiada como está', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    const item = asset({ url: 'https://cdn.brobond.com/a.png' });
    await renderReady([item]);
    fireEvent.click(screen.getByLabelText(`Mais opções para ${item.name}`));
    fireEvent.click(screen.getByRole('menuitem', { name: /Copiar URL/ }));
    expect(writeText).toHaveBeenCalledWith('https://cdn.brobond.com/a.png');
  });

  it('o aviso de cópia desaparece sozinho', async () => {
    vi.useFakeTimers();
    try {
      const writeText = vi.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
      listMock.mockResolvedValue(ok([asset()]));
      render(<Biblioteca />);
      await act(async () => {
        await Promise.resolve();
      });
      const item = screen.getByTestId('bib-grid').children[0];
      fireEvent.click(within(item as HTMLElement).getByLabelText(/Mais opções/));
      fireEvent.click(screen.getByRole('menuitem', { name: /Copiar URL/ }));
      expect(screen.getByText('URL copiada.')).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(3000);
      });
      expect(screen.queryByText('URL copiada.')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('o menu também abre o preview', async () => {
    const item = asset();
    await renderReady([item]);
    fireEvent.click(screen.getByLabelText(`Mais opções para ${item.name}`));
    fireEvent.click(screen.getByRole('menuitem', { name: /Preview/ }));
    expect(await screen.findByTestId('bib-modal')).toBeInTheDocument();
  });
});

describe('bottom sheet (mobile)', () => {
  it('abre os filtros em uma folha e escolhe a categoria por ela', async () => {
    await renderReady([asset({ kind: 'image' }), asset({ kind: 'video' })]);
    fireEvent.click(screen.getByLabelText('Abrir filtros'));
    const sheet = await screen.findByTestId('bib-sheet');
    fireEvent.click(within(sheet).getByRole('button', { name: /Imagens/ }));
    expect(screen.queryByTestId('bib-sheet')).toBeNull();
    expect(screen.getByTestId('bib-grid').children).toHaveLength(1);
  });
});
