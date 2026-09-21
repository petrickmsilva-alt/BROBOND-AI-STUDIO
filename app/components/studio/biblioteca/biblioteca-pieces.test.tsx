// @vitest-environment jsdom
/**
 * PR009.7 — as peças da Biblioteca, isoladas.
 *
 * O módulo inteiro já é exercitado em `biblioteca.test.tsx`; aqui cada peça
 * responde sozinha pelos caminhos que só ela conhece: o card sem miniatura,
 * a área pontilhada, os menus que fecham ao clicar fora, o player de vídeo
 * e os estados honestos.
 */
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { LibraryAsset } from '../../../../lib/assets/biblioteca';
import { BibliotecaCard, BibliotecaGrid, cardThumbnail } from './biblioteca-card';
import { BibliotecaDropHint, BibliotecaDropZone, BibliotecaUploadQueue } from './biblioteca-dropzone';
import { BibliotecaHeader } from './biblioteca-header';
import { BibliotecaPreview } from './biblioteca-preview';
import { BibliotecaSidebar } from './biblioteca-sidebar';
import { BibliotecaState, STATE_COPY } from './biblioteca-states';
import { CATEGORIES, type CategoryCounts } from '../../../../lib/assets/biblioteca';
import { completeUpload, createUploadItem, failUpload, markUploading, progressUpload } from '../../../../lib/assets/library';

let seq = 0;

function asset(overrides: Partial<LibraryAsset> = {}): LibraryAsset {
  seq += 1;
  return {
    id: `p-${seq}`,
    name: `Peça ${seq}.png`,
    kind: 'image',
    url: `/files/p-${seq}.png`,
    created_at: '2026-08-12T11:22:33Z',
    has_metadata: true,
    ...overrides,
  };
}

const NOOP = () => undefined;

function counts(): CategoryCounts {
  const value = {} as CategoryCounts;
  CATEGORIES.forEach(category => {
    value[category.id] = 0;
  });
  return value;
}

describe('cardThumbnail', () => {
  it('prefere a miniatura armazenada, depois a própria imagem, senão nada', () => {
    expect(cardThumbnail(asset({ thumbnail_url: '/t.jpg' }))).toBe('/t.jpg');
    expect(cardThumbnail(asset({ thumbnail_url: null, url: '/i.png' }))).toBe('/i.png');
    expect(cardThumbnail(asset({ kind: 'video', thumbnail_url: null, url: '/v.mp4' }))).toBeNull();
    expect(cardThumbnail(asset({ kind: 'image', thumbnail_url: null, url: '' }))).toBeNull();
  });
});

describe('BibliotecaCard', () => {
  function renderCard(overrides: Partial<LibraryAsset> = {}, favorite = false) {
    const item = asset(overrides);
    const onOpen = vi.fn();
    const onToggleFavorite = vi.fn();
    const onCopyUrl = vi.fn();
    render(
      <BibliotecaCard asset={item} favorite={favorite} onOpen={onOpen} onToggleFavorite={onToggleFavorite} onCopyUrl={onCopyUrl} />,
    );
    return { item, onOpen, onToggleFavorite, onCopyUrl };
  }

  it('mostra um ícone honesto quando não há miniatura — nunca um frame inventado', () => {
    renderCard({ kind: 'video', thumbnail_url: null });
    expect(screen.getByTestId(/bib-card-/)).toHaveAttribute('data-kind', 'video');
    expect(document.querySelector('.bib-card-fallback')).not.toBeNull();
    expect(document.querySelector('.bib-card-media img')).toBeNull();
  });

  it('imprime nome, resolução, tamanho e data — com — para o desconhecido', () => {
    renderCard({ name: 'Sem metadados.png', resolution: null, width: null, height: null, size_bytes: null });
    expect(screen.getByText('Sem metadados.png')).toBeInTheDocument();
    expect(screen.getAllByText('—')).toHaveLength(2);
    expect(screen.getByText('12/08/2026')).toBeInTheDocument();
  });

  it('carrega o badge de tipo e o de qualidade', () => {
    renderCard({ kind: 'audio', quality_status: 'review' });
    expect(screen.getByText('AUDIO')).toBeInTheDocument();
    expect(screen.getByText('Em revisão')).toBeInTheDocument();
  });

  it('mostra as tags derivadas dos metadados existentes', () => {
    renderCard({ tags: ['lookbook'], project: 'Brobond' });
    expect(screen.getByText('LOOKBOOK')).toBeInTheDocument();
    expect(screen.getByText('BROBOND')).toBeInTheDocument();
  });

  it('abre, favorita e copia a partir do hover', () => {
    const { item, onOpen, onToggleFavorite, onCopyUrl } = renderCard();
    fireEvent.click(screen.getByLabelText(`Visualizar ${item.name}`));
    expect(onOpen).toHaveBeenCalledWith(item);
    fireEvent.click(screen.getByLabelText(`Favoritar ${item.name}`));
    expect(onToggleFavorite).toHaveBeenCalledWith(item);
    fireEvent.click(screen.getByLabelText(`Mais opções para ${item.name}`));
    fireEvent.click(screen.getByRole('menuitem', { name: /Copiar URL/ }));
    expect(onCopyUrl).toHaveBeenCalledWith(item);
  });

  it('marca a estrela quando já é favorito e permite desmarcar', () => {
    const { item, onToggleFavorite } = renderCard({}, true);
    fireEvent.click(screen.getByLabelText(`Remover ${item.name} dos favoritos`));
    expect(onToggleFavorite).toHaveBeenCalledWith(item);
  });

  it('o menu (...) fecha ao clicar fora e ao escolher o download', () => {
    const { item } = renderCard();
    const trigger = screen.getByLabelText(`Mais opções para ${item.name}`);
    fireEvent.click(trigger);
    expect(screen.getByRole('menu')).toBeInTheDocument();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('menu')).toBeNull();
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole('menuitem', { name: /Download/ }));
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('cliques dentro do menu não o fecham', () => {
    const { item } = renderCard();
    fireEvent.click(screen.getByLabelText(`Mais opções para ${item.name}`));
    fireEvent.mouseDown(screen.getByRole('menu'));
    expect(screen.getByRole('menu')).toBeInTheDocument();
  });
});

describe('BibliotecaGrid', () => {
  it('não renderiza nada quando não há arquivos', () => {
    const { container } = render(
      <BibliotecaGrid assets={[]} favorites={new Set()} onOpen={NOOP} onToggleFavorite={NOOP} onCopyUrl={NOOP} />,
    );
    expect(container.firstChild).toBeNull();
  });
});

describe('BibliotecaSidebar', () => {
  it('lista as nove categorias com contador e marca a ativa', () => {
    render(<BibliotecaSidebar active="imagens" counts={{ ...counts(), imagens: 4 }} onSelect={NOOP} />);
    expect(screen.getByText('Categorias')).toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(9);
    expect(screen.getByTestId('bib-count-imagens')).toHaveTextContent('4');
    expect(screen.getByRole('button', { name: /Imagens/ })).toHaveAttribute('aria-current', 'true');
  });

  it('no modo compacto (bottom sheet) esconde o título mas mantém a lista', () => {
    render(<BibliotecaSidebar active="todos" counts={counts()} onSelect={NOOP} compact />);
    expect(screen.queryByText('Categorias')).toBeNull();
    expect(screen.getAllByRole('button')).toHaveLength(9);
  });

  it('um contador ausente vira zero, nunca undefined', () => {
    render(<BibliotecaSidebar active="todos" counts={{} as CategoryCounts} onSelect={NOOP} />);
    expect(screen.getByTestId('bib-count-todos')).toHaveTextContent('0');
  });

  it('reporta a categoria escolhida', () => {
    const onSelect = vi.fn();
    render(<BibliotecaSidebar active="todos" counts={counts()} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole('button', { name: /Produtos/ }));
    expect(onSelect).toHaveBeenCalledWith('produtos');
  });
});

describe('BibliotecaHeader', () => {
  function renderHeader() {
    const props = {
      search: '',
      onSearch: vi.fn(),
      category: 'todos' as const,
      onCategory: vi.fn(),
      sort: 'recentes' as const,
      onSort: vi.fn(),
      onFiles: vi.fn(),
      onOpenFilters: vi.fn(),
    };
    const view = render(<BibliotecaHeader {...props} />);
    return { ...props, view };
  }

  it('os menus fecham ao clicar fora e com Escape', () => {
    renderHeader();
    const trigger = screen.getByLabelText('Ordenar Biblioteca');
    fireEvent.click(trigger);
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('listbox')).toBeNull();
    fireEvent.click(trigger);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).toBeNull();
    // Um clique dentro do próprio menu não o fecha.
    fireEvent.click(trigger);
    fireEvent.mouseDown(screen.getByRole('listbox'));
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    // Uma tecla qualquer também não.
    fireEvent.keyDown(document, { key: 'a' });
    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });

  it('o botão de limpar só aparece com texto e zera a busca', () => {
    const onSearch = vi.fn();
    const { rerender } = render(
      <BibliotecaHeader
        search=""
        onSearch={onSearch}
        category="todos"
        onCategory={NOOP}
        sort="recentes"
        onSort={NOOP}
        onFiles={NOOP}
        onOpenFilters={NOOP}
      />,
    );
    expect(screen.queryByLabelText('Limpar pesquisa')).toBeNull();
    rerender(
      <BibliotecaHeader
        search="verao"
        onSearch={onSearch}
        category="todos"
        onCategory={NOOP}
        sort="recentes"
        onSort={NOOP}
        onFiles={NOOP}
        onOpenFilters={NOOP}
      />,
    );
    fireEvent.click(screen.getByLabelText('Limpar pesquisa'));
    expect(onSearch).toHaveBeenCalledWith('');
  });

  it('o Upload dourado abre o seletor e entrega os arquivos escolhidos', () => {
    const { onFiles } = renderHeader();
    const input = screen.getByLabelText('Selecionar arquivos para enviar');
    const click = vi.spyOn(input, 'click');
    fireEvent.click(screen.getByRole('button', { name: /Upload/ }));
    expect(click).toHaveBeenCalled();
    const file = new File(['x'], 'a.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });
    expect(onFiles).toHaveBeenCalledWith([file]);
    // Um change sem arquivos não dispara nada.
    fireEvent.change(input, { target: { files: [] } });
    expect(onFiles).toHaveBeenCalledTimes(1);
  });

  it('abre o bottom sheet pelo atalho de filtros', () => {
    const { onOpenFilters } = renderHeader();
    fireEvent.click(screen.getByLabelText('Abrir filtros'));
    expect(onOpenFilters).toHaveBeenCalled();
  });

  it('cada menu reporta a escolha', () => {
    const { onCategory, onSort } = renderHeader();
    fireEvent.click(screen.getByLabelText('Filtrar categoria'));
    fireEvent.click(screen.getByRole('option', { name: 'Favoritos' }));
    expect(onCategory).toHaveBeenCalledWith('favoritos');
    fireEvent.click(screen.getByLabelText('Ordenar Biblioteca'));
    fireEvent.click(screen.getByRole('option', { name: 'Maior arquivo' }));
    expect(onSort).toHaveBeenCalledWith('maiores');
  });

  it('a busca reporta cada tecla', () => {
    const { onSearch } = renderHeader();
    fireEvent.change(screen.getByLabelText('Pesquisar na Biblioteca'), { target: { value: 'ram' } });
    expect(onSearch).toHaveBeenCalledWith('ram');
  });
});

describe('BibliotecaDropZone e a área pontilhada', () => {
  it('mantém o overlay através dos limites dos filhos (contador de profundidade)', () => {
    render(
      <BibliotecaDropZone onFiles={NOOP}>
        <div>corpo</div>
      </BibliotecaDropZone>,
    );
    const zone = screen.getByTestId('bib-dropzone');
    const data = { dataTransfer: { files: [], types: ['Files'], dropEffect: '' } };
    fireEvent.dragEnter(zone, data);
    fireEvent.dragEnter(zone, data);
    fireEvent.dragLeave(zone, data);
    expect(screen.getByTestId('bib-drop-overlay')).toBeInTheDocument();
    fireEvent.dragLeave(zone, data);
    expect(screen.queryByTestId('bib-drop-overlay')).toBeNull();
    // O contador nunca fica negativo.
    fireEvent.dragLeave(zone, data);
    fireEvent.dragEnter(zone, data);
    expect(screen.getByTestId('bib-drop-overlay')).toBeInTheDocument();
  });

  it('ignora arrastos que não carregam arquivos', () => {
    render(
      <BibliotecaDropZone onFiles={NOOP}>
        <div>corpo</div>
      </BibliotecaDropZone>,
    );
    fireEvent.dragEnter(screen.getByTestId('bib-dropzone'), { dataTransfer: { files: [], types: ['text/plain'], dropEffect: '' } });
    expect(screen.queryByTestId('bib-drop-overlay')).toBeNull();
  });

  it('dragover marca a cópia e um drop vazio não chama o pai', () => {
    const onFiles = vi.fn();
    render(
      <BibliotecaDropZone onFiles={onFiles}>
        <div>corpo</div>
      </BibliotecaDropZone>,
    );
    const zone = screen.getByTestId('bib-dropzone');
    const transfer = { files: [], types: ['Files'], dropEffect: '' };
    fireEvent.dragOver(zone, { dataTransfer: transfer });
    expect(transfer.dropEffect).toBe('copy');
    fireEvent.drop(zone, { dataTransfer: { files: [], types: ['Files'] } });
    expect(onFiles).not.toHaveBeenCalled();
  });

  it('a área pontilhada convida e também abre o seletor', () => {
    const onFiles = vi.fn();
    render(<BibliotecaDropHint onFiles={onFiles} />);
    expect(screen.getByText('Arraste imagens e vídeos aqui')).toBeInTheDocument();
    const input = screen.getByLabelText('Selecionar arquivos para a Biblioteca');
    const click = vi.spyOn(input, 'click');
    fireEvent.click(screen.getByRole('button', { name: 'Selecionar arquivos' }));
    expect(click).toHaveBeenCalled();
    const file = new File(['x'], 'b.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });
    expect(onFiles).toHaveBeenCalledWith([file]);
    fireEvent.change(input, { target: { files: [] } });
    expect(onFiles).toHaveBeenCalledTimes(1);
  });
});

describe('BibliotecaUploadQueue', () => {
  const file = { name: 'take.mp4', type: 'video/mp4', size: 4096 };

  it('não renderiza nada com a fila vazia', () => {
    const { container } = render(<BibliotecaUploadQueue items={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('imprime nome, tamanho, percentual, velocidade e barra — nunca simulados', () => {
    const item = progressUpload(markUploading(createUploadItem('u1', file, 'video')), 2048, 4096, 1024);
    render(<BibliotecaUploadQueue items={[item]} />);
    expect(screen.getByText('take.mp4')).toBeInTheDocument();
    expect(screen.getByText('4.0 KB')).toBeInTheDocument();
    expect(screen.getByLabelText('progresso')).toHaveTextContent('50%');
    expect(screen.getByText('1.0 KB/s')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50');
    expect(screen.getByText('Enviando')).toBeInTheDocument();
  });

  it('cobre os quatro estados e mostra o erro do servidor', () => {
    const base = createUploadItem('u2', { name: 'frame.png', type: 'image/png', size: 10 }, 'image');
    render(
      <BibliotecaUploadQueue
        items={[base, completeUpload({ ...base, id: 'u2b' }), failUpload({ ...base, id: 'u3' }, 'recusado pelo servidor')]}
      />,
    );
    expect(screen.getByText('Na fila')).toBeInTheDocument();
    expect(screen.getByText('Concluído')).toBeInTheDocument();
    expect(screen.getByText('Falhou')).toBeInTheDocument();
    expect(screen.getByText('recusado pelo servidor')).toBeInTheDocument();
    // Fora do envio, a velocidade é honestamente desconhecida.
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });
});

describe('BibliotecaState', () => {
  it('cobre os cinco estados com a voz certa', () => {
    (['vazia', 'enviando', 'erro', 'offline', 'filtrada'] as const).forEach(state => {
      const view = render(<BibliotecaState state={state} />);
      expect(screen.getByTestId(`bib-state-${state}`)).toHaveAttribute(
        'role',
        state === 'erro' || state === 'offline' ? 'alert' : 'status',
      );
      expect(screen.getByText(STATE_COPY[state].title)).toBeInTheDocument();
      view.unmount();
    });
  });

  it('mostra o detalhe do servidor e a ação quando existem', () => {
    const onAction = vi.fn();
    render(<BibliotecaState state="erro" detail="503" actionLabel="Tentar novamente" onAction={onAction} />);
    expect(screen.getByText('503')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Tentar novamente/ }));
    expect(onAction).toHaveBeenCalled();
  });

  it('sem ação não inventa um botão', () => {
    render(<BibliotecaState state="vazia" actionLabel="Só o rótulo" />);
    expect(screen.queryByRole('button')).toBeNull();
  });
});

describe('BibliotecaPreview', () => {
  it('o zoom vai até o fim e o Redefinir volta ao começo', () => {
    render(<BibliotecaPreview asset={asset()} onClose={NOOP} onCopyUrl={NOOP} />);
    const zoomIn = screen.getByLabelText('Aumentar zoom');
    for (let step = 0; step < 6; step += 1) fireEvent.click(zoomIn);
    expect(screen.getByLabelText('nível de zoom')).toHaveTextContent('400%');
    expect(zoomIn).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Redefinir' }));
    expect(screen.getByLabelText('nível de zoom')).toHaveTextContent('100%');
    fireEvent.click(screen.getByLabelText('Reduzir zoom'));
    expect(screen.getByLabelText('nível de zoom')).toHaveTextContent('100%');
  });

  it('as informações podem ser escondidas e trazidas de volta', () => {
    render(<BibliotecaPreview asset={asset()} onClose={NOOP} onCopyUrl={NOOP} />);
    const toggle = screen.getByRole('button', { name: /Informações/ });
    expect(screen.getByLabelText('Informações do arquivo')).toBeInTheDocument();
    fireEvent.click(toggle);
    expect(screen.queryByLabelText('Informações do arquivo')).toBeNull();
    fireEvent.click(toggle);
    expect(screen.getByLabelText('Informações do arquivo')).toBeInTheDocument();
  });

  it('a ficha mostra os metadados existentes e — para o resto', () => {
    render(
      <BibliotecaPreview
        asset={asset({ project: 'Brobond', persona: null, provider: null, seed: null, duration_seconds: null, size_bytes: null })}
        onClose={NOOP}
        onCopyUrl={NOOP}
      />,
    );
    const facts = screen.getByLabelText('Informações do arquivo');
    expect(within(facts).getByText('Brobond')).toBeInTheDocument();
    expect(within(facts).getAllByText('—').length).toBeGreaterThanOrEqual(5);
  });

  it('o vídeo usa a miniatura armazenada como poster, e — sem ela — nenhum', () => {
    const withPoster = render(
      <BibliotecaPreview asset={asset({ kind: 'video', url: '/v.mp4', thumbnail_url: '/t.jpg' })} onClose={NOOP} onCopyUrl={NOOP} />,
    );
    expect(document.querySelector('video')).toHaveAttribute('poster', '/t.jpg');
    withPoster.unmount();
    render(<BibliotecaPreview asset={asset({ kind: 'video', url: '/v.mp4', thumbnail_url: null })} onClose={NOOP} onCopyUrl={NOOP} />);
    expect(document.querySelector('video')).not.toHaveAttribute('poster');
  });

  it('a ficha imprime a duração quando o arquivo a carrega', () => {
    render(<BibliotecaPreview asset={asset({ duration_seconds: 65, seed: 42, provider: 'wan', persona: 'Ayla' })} onClose={NOOP} onCopyUrl={NOOP} />);
    const facts = screen.getByLabelText('Informações do arquivo');
    expect(within(facts).getByText('01:05')).toBeInTheDocument();
    expect(within(facts).getByText('42')).toBeInTheDocument();
    expect(within(facts).getByText('wan')).toBeInTheDocument();
    expect(within(facts).getByText('Ayla')).toBeInTheDocument();
  });

  it('a ficha lista as tags derivadas', () => {
    render(<BibliotecaPreview asset={asset({ tags: ['ram2026'] })} onClose={NOOP} onCopyUrl={NOOP} />);
    expect(within(screen.getByLabelText('Informações do arquivo')).getByText('RAM2026')).toBeInTheDocument();
  });

  it('mostra o aviso transitório de cópia quando o pai manda um', () => {
    render(<BibliotecaPreview asset={asset()} onClose={NOOP} onCopyUrl={NOOP} copyNotice="URL copiada." />);
    expect(screen.getByText('URL copiada.')).toBeInTheDocument();
  });

  it('fecha pelo fundo e pelo X', () => {
    const onClose = vi.fn();
    render(<BibliotecaPreview asset={asset()} onClose={onClose} onCopyUrl={NOOP} />);
    fireEvent.click(screen.getAllByLabelText('Fechar preview')[0]);
    fireEvent.click(screen.getAllByLabelText('Fechar preview')[1]);
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('teclas que não são Escape não fecham', () => {
    const onClose = vi.fn();
    render(<BibliotecaPreview asset={asset()} onClose={onClose} onCopyUrl={NOOP} />);
    fireEvent.keyDown(window, { key: 'Enter' });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('copia a URL a partir do cabeçalho', () => {
    const onCopyUrl = vi.fn();
    const item = asset();
    render(<BibliotecaPreview asset={item} onClose={NOOP} onCopyUrl={onCopyUrl} />);
    fireEvent.click(screen.getByRole('button', { name: /Copiar URL/ }));
    expect(onCopyUrl).toHaveBeenCalledWith(item);
  });

  describe('player de vídeo', () => {
    function renderVideo() {
      const item = asset({ kind: 'video', name: 'Take.mp4', url: '/files/take.mp4', thumbnail_url: '/t.jpg' });
      render(<BibliotecaPreview asset={item} onClose={NOOP} onCopyUrl={NOOP} />);
      const video = document.querySelector('video') as HTMLVideoElement;
      return { item, video };
    }

    it('toca, pausa e reage ao fim do arquivo', () => {
      const { video } = renderVideo();
      const play = vi.spyOn(video, 'play').mockImplementation(() => {
        Object.defineProperty(video, 'paused', { value: false, configurable: true });
        return Promise.resolve();
      });
      const pause = vi.spyOn(video, 'pause').mockImplementation(() => {
        Object.defineProperty(video, 'paused', { value: true, configurable: true });
      });
      fireEvent.click(screen.getByLabelText('Reproduzir'));
      expect(play).toHaveBeenCalled();
      fireEvent.click(screen.getByLabelText('Pausar'));
      expect(pause).toHaveBeenCalled();
      fireEvent.click(screen.getByLabelText('Reproduzir'));
      fireEvent.ended(video);
      expect(screen.getByLabelText('Reproduzir')).toBeInTheDocument();
    });

    it('a timeline mostra a duração real e busca no arquivo', () => {
      const { video } = renderVideo();
      expect(screen.getAllByText('—').length).toBeGreaterThan(0);
      Object.defineProperty(video, 'duration', { value: 90, configurable: true });
      fireEvent.loadedMetadata(video);
      expect(screen.getByText('01:30')).toBeInTheDocument();
      fireEvent.change(screen.getByLabelText('Linha do tempo'), { target: { value: '30' } });
      expect(video.currentTime).toBe(30);
      expect(screen.getByText('00:30')).toBeInTheDocument();
      Object.defineProperty(video, 'currentTime', { value: 45, configurable: true, writable: true });
      fireEvent.timeUpdate(video);
      expect(screen.getByText('00:45')).toBeInTheDocument();
    });

    it('o volume muda, zera e silencia', () => {
      const { video } = renderVideo();
      fireEvent.change(screen.getByLabelText('Volume'), { target: { value: '0.5' } });
      expect(video.volume).toBeCloseTo(0.5);
      expect(screen.getByLabelText('Silenciar')).toBeInTheDocument();
      fireEvent.change(screen.getByLabelText('Volume'), { target: { value: '0' } });
      expect(screen.getByLabelText('Ativar som')).toBeInTheDocument();
      fireEvent.click(screen.getByLabelText('Ativar som'));
      expect(screen.getByLabelText('Silenciar')).toBeInTheDocument();
    });

    it('tela cheia usa a API do navegador quando ela existe', () => {
      const { video } = renderVideo();
      const stage = video.parentElement as HTMLElement;
      const request = vi.fn().mockResolvedValue(undefined);
      Object.defineProperty(stage, 'requestFullscreen', { value: request, configurable: true });
      fireEvent.click(screen.getByLabelText('Tela cheia'));
      expect(request).toHaveBeenCalled();
    });

    it('sem a API de tela cheia o botão simplesmente não faz nada', () => {
      const { video } = renderVideo();
      const stage = video.parentElement as HTMLElement;
      Object.defineProperty(stage, 'requestFullscreen', { value: undefined, configurable: true });
      expect(() => fireEvent.click(screen.getByLabelText('Tela cheia'))).not.toThrow();
    });

    it('áudio usa o mesmo palco, sem poster', () => {
      render(
        <BibliotecaPreview
          asset={asset({ kind: 'audio', name: 'Trilha.mp3', url: '/files/t.mp3', thumbnail_url: '/x.jpg' })}
          onClose={NOOP}
          onCopyUrl={NOOP}
        />,
      );
      expect(screen.getByTestId('bib-stage-video')).toBeInTheDocument();
      expect(document.querySelector('video')).not.toHaveAttribute('poster');
    });
  });
});
