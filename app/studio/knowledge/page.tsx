'use client';

/**
 * V3.1 — /studio/knowledge: the Cinematic Knowledge Graph.
 *
 * Nodes, edges, semantic search and filters. Everything is the real API:
 * the graph is persisted in PostgreSQL (canonical catalog in the global
 * workspace, your nodes in your workspace) and the search box answers with
 * complete entities ("RAM branca" -> the full Vehicle).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft,
  Boxes,
  Loader2,
  Network,
  Plus,
  Search,
  SearchX,
  X,
} from 'lucide-react';
import type {
  GraphNode,
  GraphNodeType,
  GraphRelationship,
  KnowledgeGraph,
  RelationVocabularyEntry,
  SemanticMatch,
} from '../../../lib/api';
import {
  createGraphRelationship,
  createGraphNode,
  deleteGraphRelationship,
  deleteGraphNode,
  getKnowledgeGraph,
  getRelationVocabulary,
  searchKnowledgeGraph,
} from '../../../lib/api';
import KnowledgeCanvas, { ENTITY_TYPE_META } from './KnowledgeCanvas';
import KnowledgeNodePanel from './KnowledgeNodePanel';

const ALL_TYPES = Object.keys(ENTITY_TYPE_META) as GraphNodeType[];

export default function KnowledgePage() {
  const [graph, setGraph] = useState<KnowledgeGraph | null>(null);
  const [vocabulary, setVocabulary] = useState<RelationVocabularyEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<GraphNodeType | 'all'>('all');
  const [relationFilter, setRelationFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<SemanticMatch[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  // create form state
  const [creating, setCreating] = useState(false);
  const [newType, setNewType] = useState<GraphNodeType>('character');
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');

  const refresh = useCallback(async () => {
    const result = await getKnowledgeGraph();
    if (result.remote) {
      setGraph(result.data);
      setOffline(null);
    } else {
      setOffline(result.error === 'offline' ? 'API offline — inicie o FastAPI para ver o grafo.' : result.error ?? 'erro');
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    getRelationVocabulary().then(result => {
      if (result.remote) setVocabulary(result.data);
    });
    void refresh();
  }, [refresh]);

  const runSearch = async () => {
    if (!search.trim()) return;
    setSearching(true);
    const result = await searchKnowledgeGraph(search.trim(), typeFilter === 'all' ? undefined : typeFilter);
    if (result.remote) {
      setSearchResults(result.data.results);
    } else {
      setNotice(result.error === 'offline' ? 'Busca indisponível: API offline.' : result.error ?? null);
    }
    setSearching(false);
  };

  const pickResult = (match: SemanticMatch) => {
    setSelectedId(match.node.id);
    setSearchResults(null);
  };

  const filteredNodes = useMemo(() => {
    if (!graph) return [];
    const bySelectedType = typeFilter === 'all' ? graph.nodes : graph.nodes.filter(n => n.entity_type === typeFilter);
    if (relationFilter === 'all') return bySelectedType;
    const relatedIds = new Set<string>();
    for (const rel of graph.relationships) {
      if (rel.relation_type !== relationFilter) continue;
      relatedIds.add(rel.source_id);
      relatedIds.add(rel.target_id);
    }
    return bySelectedType.filter(n => relatedIds.has(n.id) || n.is_canonical === false && relatedIds.size === 0);
  }, [graph, typeFilter, relationFilter]);

  const filteredRelationships = useMemo(() => {
    if (!graph) return [];
    const visibleIds = new Set(filteredNodes.map(n => n.id));
    return graph.relationships.filter(rel =>
      visibleIds.has(rel.source_id) &&
      visibleIds.has(rel.target_id) &&
      (relationFilter === 'all' || rel.relation_type === relationFilter),
    );
  }, [graph, filteredNodes, relationFilter]);

  const selectedNode: GraphNode | null = graph?.nodes.find(n => n.id === selectedId) ?? null;
  const selectedRelationships: GraphRelationship[] = selectedNode
    ? graph!.relationships.filter(rel => rel.source_id === selectedNode.id || rel.target_id === selectedNode.id)
    : [];
  const highlightIds = useMemo(() => {
    if (!selectedNode) return new Set<string>();
    const ids = new Set<string>([selectedNode.id]);
    for (const rel of graph?.relationships ?? []) {
      if (rel.source_id === selectedNode.id) ids.add(rel.target_id);
      if (rel.target_id === selectedNode.id) ids.add(rel.source_id);
    }
    return ids;
  }, [selectedNode, graph]);

  const relationTypes = vocabulary.length > 0 ? vocabulary.map(v => v.type) : Array.from(new Set((graph?.relationships ?? []).map(r => r.relation_type)));

  const submitCreate = async () => {
    if (!newName.trim()) return;
    setBusy(true);
    setNotice(null);
    const result = await createGraphNode({ entity_type: newType, name: newName.trim(), description: newDescription.trim() });
    if (result.remote) {
      setCreating(false);
      setNewName('');
      setNewDescription('');
      setSelectedId(result.data.id);
      await refresh();
    } else {
      setNotice(result.error === 'offline' ? 'API offline — não foi possível criar o nó.' : result.error ?? 'falha');
    }
    setBusy(false);
  };

  const handleDeleteNode = async () => {
    if (!selectedNode) return;
    setBusy(true);
    const result = await deleteGraphNode(selectedNode.id);
    if (result.remote) {
      setSelectedId(null);
      await refresh();
    } else {
      setNotice(result.error ?? 'falha ao remover');
    }
    setBusy(false);
  };

  const handleDeleteRelationship = async (relationshipId: string) => {
    setBusy(true);
    const result = await deleteGraphRelationship(relationshipId);
    if (result.remote) await refresh();
    else setNotice(result.error ?? 'falha ao remover a relação');
    setBusy(false);
  };

  const handleCreateRelationship = async (targetId: string, relationType: string) => {
    if (!selectedNode) return;
    setBusy(true);
    const result = await createGraphRelationship({ source_id: selectedNode.id, target_id: targetId, relation_type: relationType });
    if (result.remote) {
      setNotice(null);
      await refresh();
    } else {
      setNotice(result.error === 'offline' ? 'API offline — não foi possível criar a relação.' : result.error ?? 'falha');
    }
    setBusy(false);
  };

  const relationTypesInGraph = graph ? Object.keys(graph.counts.by_relation) : [];

  return (
    <main className="knowledge-page">
      <section className="knowledge-hero">
        <div>
          <div className="eyebrow"><Network size={13} /> V3.1 · CINEMATIC KNOWLEDGE GRAPH</div>
          <h1>Memória que virou mapa: quem dirige o quê, quem veste o quê, o que pertence a quem.</h1>
          <p>Character, Brand, Campaign, Location, Vehicle, Wardrobe e Prop — todas relacionáveis. O catálogo do BROBOND é somente leitura; os seus nós vivem no seu workspace.</p>
        </div>
        <div className="knowledge-stats">
          {graph && (
            <>
              <span><Boxes size={14} /> {graph.counts.nodes} nós</span>
              <span><Network size={14} /> {graph.counts.relationships} relações</span>
              <span>{ALL_TYPES.filter(t => (graph.counts.by_type[t] ?? 0) > 0).length} tipos</span>
            </>
          )}
          <a className="secondary-button" href="/"><ArrowLeft size={13} /> Estúdio</a>
        </div>
      </section>

      {offline && <div className="knowledge-offline"><SearchX size={15} /> {offline}</div>}
      {notice && <div className="knowledge-notice" onClick={() => setNotice(null)}><SearchX size={14} /> {notice}</div>}

      <section className="knowledge-toolbar">
        <div className="knowledge-search">
          <Search size={15} />
          <input
            value={search}
            placeholder='Busca semântica — ex.: "RAM branca" ou "Showroom"'
            onChange={event => setSearch(event.target.value)}
            onKeyDown={event => event.key === 'Enter' && void runSearch()}
          />
          <button type="button" className="secondary-button" onClick={() => void runSearch()} disabled={searching || !search.trim()}>
            {searching ? <Loader2 size={14} className="spin" /> : <Search size={14} />} Buscar
          </button>
          {searchResults !== null && (
            <button type="button" className="icon-button" title="Limpar busca" onClick={() => setSearchResults(null)}>
              <X size={14} />
            </button>
          )}
        </div>
        <div className="knowledge-filters">
          <button type="button" className={`knowledge-chip ${typeFilter === 'all' ? 'active' : ''}`} onClick={() => setTypeFilter('all')}>
            Todos
          </button>
          {ALL_TYPES.map(type => (
            <button
              key={type}
              type="button"
              className={`knowledge-chip ${typeFilter === type ? 'active' : ''}`}
              style={typeFilter === type ? { borderColor: ENTITY_TYPE_META[type].color, color: ENTITY_TYPE_META[type].color } : undefined}
              onClick={() => setTypeFilter(type)}
            >
              <i style={{ background: ENTITY_TYPE_META[type].color }} />
              {ENTITY_TYPE_META[type].label}
            </button>
          ))}
          <select value={relationFilter} onChange={event => setRelationFilter(event.target.value)}>
            <option value="all">Todas as relações</option>
            {relationTypesInGraph.map(type => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>
        </div>
      </section>

      {searchResults !== null && (
        <section className="knowledge-search-results">
          <h3><Search size={14} /> "{search.trim()}"</h3>
          {searchResults.length === 0 ? (
            <p className="muted">Nenhuma entidade corresponde — a busca não inventa: sem correspondência, resposta vazia.</p>
          ) : (
            searchResults.map(match => (
              <button type="button" key={match.node.id} className="knowledge-search-row" onClick={() => pickResult(match)}>
                <span className="knowledge-type-badge" style={{ color: ENTITY_TYPE_META[match.node.entity_type]?.color, borderColor: ENTITY_TYPE_META[match.node.entity_type]?.color }}>
                  {ENTITY_TYPE_META[match.node.entity_type]?.label ?? match.node.entity_type}
                </span>
                <span className="knowledge-search-name">{match.node.name}</span>
                <span className="muted small">
                  {match.node.description || Object.entries(match.node.attributes).map(([k, v]) => `${k}: ${v}`).join(' · ') || 'sem descrição'}
                </span>
                <span className="knowledge-search-score">score {match.score}</span>
              </button>
            ))
          )}
        </section>
      )}

      <section className="knowledge-workspace">
        <div className="knowledge-canvas-wrap">
          {loading ? (
            <div className="knowledge-loading"><Loader2 size={20} className="spin" /> Carregando o grafo…</div>
          ) : (
            <KnowledgeCanvas
              nodes={filteredNodes}
              relationships={filteredRelationships}
              selectedId={selectedId}
              highlightIds={highlightIds}
              onSelect={setSelectedId}
            />
          )}
        </div>

        {selectedNode ? (
          <KnowledgeNodePanel
            node={selectedNode}
            relationships={selectedRelationships}
            candidates={graph?.nodes.filter(n => n.id !== selectedNode.id) ?? []}
            relationTypes={relationTypes}
            onDeleteNode={() => void handleDeleteNode()}
            onDeleteRelationship={id => void handleDeleteRelationship(id)}
            onCreateRelationship={(target, type) => void handleCreateRelationship(target, type)}
          />
        ) : (
          <aside className="control-panel knowledge-panel">
            <div className="panel-heading">
              <span>Novo nó</span>
              <span className="muted">seu workspace</span>
            </div>
            <p className="muted small">
              Clique num nó do mapa para ver atributos, relações (nas duas direções) e ações. Ou crie um novo:
            </p>
            <label>
              Tipo
              <select value={newType} onChange={event => setNewType(event.target.value as GraphNodeType)}>
                {ALL_TYPES.map(type => <option key={type} value={type}>{ENTITY_TYPE_META[type].label}</option>)}
              </select>
            </label>
            <label>
              Nome
              <input value={newName} placeholder="ex.: Caminhão XLR" onChange={event => setNewName(event.target.value)} />
            </label>
            <label>
              Descrição
              <input value={newDescription} placeholder="opcional" onChange={event => setNewDescription(event.target.value)} />
            </label>
            <button type="button" className="primary-button full" disabled={busy || !newName.trim()} onClick={() => void submitCreate()}>
              {busy ? <Loader2 size={15} className="spin" /> : <Plus size={15} />} Criar nó
            </button>
          </aside>
        )}
      </section>
    </main>
  );
}
