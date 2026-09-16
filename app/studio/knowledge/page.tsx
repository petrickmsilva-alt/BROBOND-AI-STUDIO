'use client';

import { useEffect, useMemo, useState } from 'react';
import { Database, Network, RefreshCcw, Search, X, XCircle } from 'lucide-react';
import type {
  GraphCharacterContext,
  GraphEdge,
  GraphNeighborhood,
  GraphNode,
  GraphQueryMatch,
} from '../../../lib/api';
import {
  graphCharacterContext,
  graphNeighbors,
  listGraphEdges,
  listGraphNodes,
  queryGraph,
  seedGraphDemo,
} from '../../../lib/api';
import {
  colorForEntity,
  edgeMidpoint,
  edgePath,
  layoutRadial,
  truncateLabel,
} from '../../../lib/graph/layout';

const CANVAS_WIDTH = 860;
const CANVAS_HEIGHT = 520;

const ENTITY_FILTERS: Array<{ id: string; label: string }> = [
  { id: 'all', label: 'Todos' },
  { id: 'character', label: 'Personagens' },
  { id: 'brand', label: 'Marcas' },
  { id: 'campaign', label: 'Campanhas' },
  { id: 'location', label: 'Lugares' },
  { id: 'vehicle', label: 'Veículos' },
  { id: 'wardrobe', label: 'Figurino' },
  { id: 'prop', label: 'Objetos' },
];

function formatAttribute(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export default function KnowledgePage() {
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [nodeTotal, setNodeTotal] = useState(0);
  const [edgeTotal, setEdgeTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const [query, setQuery] = useState('');
  const [matches, setMatches] = useState<GraphQueryMatch[] | null>(null);
  const [searchedTerm, setSearchedTerm] = useState('');
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | undefined>();

  const [entityFilter, setEntityFilter] = useState('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [neighborhood, setNeighborhood] = useState<GraphNeighborhood | null>(null);
  const [characterContext, setCharacterContext] = useState<GraphCharacterContext | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | undefined>();

  const [seeding, setSeeding] = useState(false);
  const [seedMessage, setSeedMessage] = useState<string | undefined>();

  const load = async () => {
    setLoading(true);
    setError(undefined);
    const [nodesResult, edgesResult] = await Promise.all([
      listGraphNodes({ limit: 200 }),
      listGraphEdges({ limit: 500 }),
    ]);
    if (nodesResult.remote && edgesResult.remote) {
      setNodes(nodesResult.data.nodes);
      setNodeTotal(nodesResult.data.total);
      setEdges(edgesResult.data.edges);
      setEdgeTotal(edgesResult.data.total);
    } else {
      setNodes([]);
      setEdges([]);
      setNodeTotal(0);
      setEdgeTotal(0);
      const problem = !nodesResult.remote ? nodesResult : edgesResult;
      setError(
        problem.error === 'offline'
          ? 'API offline — inicie o FastAPI para explorar o Knowledge Graph.'
          : problem.error,
      );
    }
    setLoading(false);
  };

  const runSearch = async () => {
    const term = query.trim();
    if (!term) {
      setMatches(null);
      setSearchedTerm('');
      setSearchError(undefined);
      return;
    }
    setSearching(true);
    setSearchError(undefined);
    const result = await queryGraph(term, { limit: 10 });
    if (result.remote) {
      setMatches(result.data.matches);
      setSearchedTerm(term);
    } else {
      setMatches([]);
      setSearchedTerm(term);
      setSearchError(
        result.error === 'offline' ? 'API offline — sem resposta para a busca.' : result.error,
      );
    }
    setSearching(false);
  };

  const clearSelection = () => {
    setSelectedId(null);
    setNeighborhood(null);
    setCharacterContext(null);
    setDetailError(undefined);
  };

  const selectNode = async (nodeId: string) => {
    if (nodeId === selectedId) {
      clearSelection();
      return;
    }
    setEntityFilter('all');
    setSelectedId(nodeId);
    setDetailLoading(true);
    setNeighborhood(null);
    setCharacterContext(null);
    setDetailError(undefined);
    const node = nodes.find(item => item.id === nodeId);
    const [neighborsResult, contextResult] = await Promise.all([
      graphNeighbors(nodeId, { depth: 1, direction: 'both' }),
      node?.entity_type === 'character'
        ? graphCharacterContext(node.name)
        : Promise.resolve(null),
    ]);
    if (neighborsResult.remote) {
      setNeighborhood(neighborsResult.data);
    } else {
      setDetailError(
        neighborsResult.error === 'offline'
          ? 'API offline — vizinhança indisponível.'
          : (neighborsResult.error ?? 'Vizinhança indisponível.'),
      );
    }
    if (contextResult?.remote) setCharacterContext(contextResult.data);
    setDetailLoading(false);
  };

  const seed = async () => {
    setSeeding(true);
    setSeedMessage(undefined);
    const result = await seedGraphDemo();
    if (result.remote) {
      const report = result.data;
      setSeedMessage(
        `Demonstração carregada: ${report.created_nodes} nós e ${report.created_edges} arestas novos ` +
          `(${report.skipped_nodes + report.skipped_edges} já existiam).`,
      );
      await load();
    } else {
      setSeedMessage(
        result.error === 'offline'
          ? 'API offline — não foi possível carregar a demonstração.'
          : result.error,
      );
    }
    setSeeding(false);
  };

  useEffect(() => {
    load();
  }, []);

  const filterCounts = useMemo(() => {
    const counts: Record<string, number> = { all: nodes.length };
    for (const node of nodes) counts[node.entity_type] = (counts[node.entity_type] ?? 0) + 1;
    return counts;
  }, [nodes]);

  const visibleNodes = useMemo(
    () => (entityFilter === 'all' ? nodes : nodes.filter(node => node.entity_type === entityFilter)),
    [nodes, entityFilter],
  );

  const visibleEdges = useMemo(() => {
    const visible = new Set(visibleNodes.map(node => node.id));
    return edges.filter(edge => visible.has(edge.source_id) && visible.has(edge.target_id));
  }, [edges, visibleNodes]);

  const positions = useMemo(
    () =>
      layoutRadial(visibleNodes, {
        width: CANVAS_WIDTH,
        height: CANVAS_HEIGHT,
        centerId: selectedId,
      }),
    [visibleNodes, selectedId],
  );

  const highlight = useMemo(() => {
    if (!selectedId) return null;
    return new Set([selectedId, ...(neighborhood?.nodes.map(node => node.id) ?? [])]);
  }, [selectedId, neighborhood]);

  const selected = nodes.find(node => node.id === selectedId) ?? null;

  return <main className="knowledge-page">
    <section className="knowledge-hero">
      <div>
        <div className="eyebrow"><Network size={13} /> V3.1 · CINEMATIC KNOWLEDGE GRAPH</div>
        <h1>Todo o universo BROBOND num grafo só.</h1>
        <p>Personagens, marcas, campanhas, lugares, veículos, figurino e objetos — e as relações
          entre eles. Busca semântica em PT/EN, vizinhança em 1–2 saltos e contexto de personagem
          para o Director AI.</p>
      </div>
      <div className="knowledge-hero-actions">
        <button type="button" className="primary-button" onClick={load} disabled={loading}>
          <RefreshCcw size={15} /> {loading ? 'Carregando…' : 'Atualizar'}
        </button>
        <button type="button" className="knowledge-ghost" onClick={seed} disabled={seeding}>
          <Database size={15} /> {seeding ? 'Carregando…' : 'Demonstração'}
        </button>
      </div>
    </section>

    {error && <div className="knowledge-error"><XCircle size={15} /> {error}</div>}

    <section className="knowledge-toolbar" aria-label="Busca e filtros">
      <form
        className="knowledge-search"
        onSubmit={event => {
          event.preventDefault();
          runSearch();
        }}
      >
        <input
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="Buscar no grafo — ex. RAM branca, Showroom, Petrick…"
          aria-label="Buscar no grafo"
        />
        <button type="submit" className="primary-button" disabled={searching}>
          <Search size={15} /> {searching ? 'Buscando…' : 'Buscar'}
        </button>
      </form>
      <div className="knowledge-filters">
        {ENTITY_FILTERS.map(filter => (
          <button
            key={filter.id}
            type="button"
            className={entityFilter === filter.id ? 'active' : ''}
            onClick={() => setEntityFilter(filter.id)}
          >
            {filter.label} · {filterCounts[filter.id] ?? 0}
          </button>
        ))}
        {!loading && !error && <span className="knowledge-counts">{nodeTotal} nós · {edgeTotal} arestas</span>}
      </div>
    </section>

    {seedMessage && <p className="knowledge-seed-note">{seedMessage}</p>}

    {matches !== null && <section className="knowledge-results" aria-label="Resultados da busca">
      <h2>{matches.length} resultado(s) para “{searchedTerm}”</h2>
      {searchError && <div className="knowledge-error"><XCircle size={15} /> {searchError}</div>}
      {matches.map(match => (
        <button
          key={match.node.id}
          type="button"
          className="knowledge-result"
          onClick={() => selectNode(match.node.id)}
        >
          <span>
            <strong>{match.node.name}</strong>
            <span className="result-meta">{match.node.entity_type} · {match.matched_fields.join(', ')}</span>
          </span>
          <span className="result-score">pontuação {match.score}</span>
        </button>
      ))}
    </section>}

    {!loading && !error && nodes.length === 0 && <div className="knowledge-empty">
      <div className="empty-icon"><Network size={24} /></div>
      <h3>Grafo vazio</h3>
      <p>Nenhum nó neste workspace ainda. Carregue a demonstração — Petrick, RAM, BroBond — ou volte quando o grafo tiver dados.</p>
      <button type="button" className="primary-button" onClick={seed} disabled={seeding}>
        <Database size={15} /> {seeding ? 'Carregando…' : 'Carregar demonstração'}
      </button>
    </div>}

    {(nodes.length > 0 || loading) && <section className="knowledge-workbench">
      <div className="knowledge-canvas">
        <svg
          className="knowledge-graph-svg"
          viewBox={`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`}
          role="img"
          aria-label={`Grafo com ${visibleNodes.length} nós e ${visibleEdges.length} arestas`}
        >
          <title>{`Grafo com ${visibleNodes.length} nós e ${visibleEdges.length} arestas`}</title>
          {visibleEdges.map(edge => {
            const from = positions[edge.source_id];
            const to = positions[edge.target_id];
            if (!from || !to) return null;
            const mid = edgeMidpoint(from, to);
            const inScope = !highlight || (highlight.has(edge.source_id) && highlight.has(edge.target_id));
            return <g key={edge.id} className={inScope ? '' : 'dimmed'}>
              <path d={edgePath(from, to)} className="k-edge" />
              <text x={mid.x} y={mid.y - 4} textAnchor="middle" className="k-edge-label">
                {edge.relation}
              </text>
            </g>;
          })}
          {visibleNodes.map(node => {
            const pos = positions[node.id];
            if (!pos) return null;
            const isSelected = node.id === selectedId;
            const inScope = !highlight || highlight.has(node.id);
            return <g
              key={node.id}
              transform={`translate(${pos.x} ${pos.y})`}
              className={`k-node${isSelected ? ' selected' : ''}${inScope ? '' : ' dimmed'}`}
              onClick={() => selectNode(node.id)}
              onKeyDown={event => {
                if (event.key === 'Enter' || event.key === ' ') selectNode(node.id);
              }}
              tabIndex={0}
              role="button"
              aria-label={`${node.name}, ${node.entity_type}`}
            >
              <title>{`${node.name} · ${node.entity_type}`}</title>
              <circle r={isSelected ? 13 : 10} fill={colorForEntity(node.entity_type)} />
              <text y={26} textAnchor="middle" className="k-node-label">{truncateLabel(node.name)}</text>
            </g>;
          })}
        </svg>
      </div>

      <aside className="knowledge-detail" aria-label="Detalhe do nó">
        {!selected && !detailLoading && <p className="knowledge-hint">
          Selecione um nó no grafo para ver atributos, apelidos e vizinhança. Personagens mostram
          ainda o contexto que o Director AI recebe.
        </p>}
        {detailLoading && <p className="knowledge-hint">Carregando vizinhança…</p>}
        {detailError && <div className="knowledge-detail-error"><XCircle size={14} /> {detailError}</div>}
        {selected && <>
          <div className="knowledge-detail-head">
            <div>
              <span className="knowledge-type-chip">{selected.entity_type}</span>
              <h2>{selected.name}</h2>
            </div>
            <button type="button" onClick={clearSelection} aria-label="Limpar seleção"><X size={16} /></button>
          </div>
          <dl className="knowledge-meta">
            <div><dt>Slug</dt><dd>{selected.slug}</dd></div>
            <div><dt>Apelidos</dt><dd>{selected.aliases.length > 0 ? selected.aliases.join(', ') : '—'}</dd></div>
            {Object.entries(selected.attributes).map(([key, value]) => (
              <div key={key}><dt>{key}</dt><dd>{formatAttribute(value)}</dd></div>
            ))}
          </dl>
          {neighborhood && <>
            <h3 className="knowledge-section-title">Vizinhança · {neighborhood.nodes.length}</h3>
            <div className="knowledge-neighbors">
              {neighborhood.nodes.length === 0 && <p className="knowledge-hint">Sem vizinhos em 1 salto.</p>}
              {neighborhood.nodes.map(neighbor => (
                <button
                  key={neighbor.id}
                  type="button"
                  className="knowledge-neighbor"
                  onClick={() => selectNode(neighbor.id)}
                >
                  {neighbor.name} <small>{neighbor.entity_type}</small>
                </button>
              ))}
            </div>
          </>}
          {characterContext?.found && <>
            <h3 className="knowledge-section-title">Contexto do Director AI</h3>
            <div className="knowledge-chip-row">
              {Object.entries(characterContext.relation_counts).map(([relation, count]) => (
                <span key={relation}>{relation} ×{count}</span>
              ))}
            </div>
            <ul className="knowledge-phrases">
              {characterContext.phrases.map(phrase => <li key={phrase}>{phrase}</li>)}
            </ul>
            <div className="knowledge-relations">
              {characterContext.relations.map(relation => (
                <div className="knowledge-relation" key={`${relation.relation}-${relation.peer.id}`}>
                  <span>{relation.phrase}</span>
                  <button
                    type="button"
                    className="knowledge-neighbor"
                    onClick={() => selectNode(relation.peer.id)}
                  >
                    {relation.peer.name} <small>{relation.peer.entity_type}</small>
                  </button>
                </div>
              ))}
            </div>
          </>}
        </>}
      </aside>
    </section>}
  </main>;
}
