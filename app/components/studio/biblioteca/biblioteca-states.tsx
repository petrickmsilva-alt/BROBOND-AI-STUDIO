'use client';

/**
 * PR009.7 — Biblioteca Criativa: os estados honestos.
 *
 * Vazia, enviando, sem conexão, erro e "os filtros cortaram tudo". O texto
 * nunca afirma mais do que se sabe: sem resposta da API dizemos exatamente
 * isso, e o erro do servidor aparece com as palavras dele.
 */
import { CloudOff, Library, RefreshCw, ScanSearch, TriangleAlert, UploadCloud } from 'lucide-react';

export type BibliotecaStateId = 'vazia' | 'enviando' | 'erro' | 'offline' | 'filtrada';

export const STATE_COPY: Record<
  BibliotecaStateId,
  { icon: React.ReactNode; eyebrow: string; title: string; body: string }
> = {
  vazia: {
    icon: <Library size={24} aria-hidden="true" />,
    eyebrow: 'BIBLIOTECA',
    title: 'Nada na prateleira ainda.',
    body: 'Arraste imagens e vídeos para qualquer ponto desta página — PNG, JPG, WEBP, MP4 ou MOV — e eles entram no acervo com os metadados intactos.',
  },
  enviando: {
    icon: <UploadCloud size={24} aria-hidden="true" />,
    eyebrow: 'ENVIO',
    title: 'Recebendo seu material…',
    body: 'Os arquivos estão sendo gravados com miniatura e metadados. A fila acima mostra o percentual real de cada um.',
  },
  erro: {
    icon: <TriangleAlert size={24} aria-hidden="true" />,
    eyebrow: 'ALGO QUEBROU',
    title: 'Não foi possível ler a Biblioteca.',
    body: 'A API respondeu com um erro. Tente novamente — se persistir, a mensagem abaixo é a resposta exata do servidor.',
  },
  offline: {
    icon: <CloudOff size={24} aria-hidden="true" />,
    eyebrow: 'SEM CONEXÃO',
    title: 'O estúdio não alcançou a API.',
    body: 'Nenhuma resposta chegou do backend. Verifique a conexão ou suba o FastAPI — seus arquivos seguem seguros até lá.',
  },
  filtrada: {
    icon: <ScanSearch size={24} aria-hidden="true" />,
    eyebrow: 'FILTROS',
    title: 'Nenhum arquivo neste recorte.',
    body: 'Troque a categoria ou limpe a pesquisa — a Biblioteca continua inteira por baixo.',
  },
};

export function BibliotecaState({
  state,
  detail,
  actionLabel,
  onAction,
}: {
  state: BibliotecaStateId;
  detail?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  const copy = STATE_COPY[state];
  return (
    <div
      className={`bib-state bib-state-${state}`}
      role={state === 'erro' || state === 'offline' ? 'alert' : 'status'}
      data-testid={`bib-state-${state}`}
    >
      <span className="bib-state-icon">{copy.icon}</span>
      <span className="bib-state-eyebrow">{copy.eyebrow}</span>
      <h2>{copy.title}</h2>
      <p>{copy.body}</p>
      {detail && <code>{detail}</code>}
      {actionLabel && onAction && (
        <button type="button" className="bib-state-action" onClick={onAction}>
          <RefreshCw size={14} aria-hidden="true" /> {actionLabel}
        </button>
      )}
    </div>
  );
}
