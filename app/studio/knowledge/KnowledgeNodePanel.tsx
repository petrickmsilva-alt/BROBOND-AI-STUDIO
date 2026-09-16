'use client';

/**
 * V3.1 — the selected entity: attributes, its relationships read from its
 * side (outgoing with the relation label, incoming with the reverse one),
 * and the workspace actions (delete, link). Canonical rows are read-only and
 * the panel says so instead of offering a disabled button.
 */
import { useState } from 'react';
import { ArrowLeftRight, Ban, Link2, Trash2 } from 'lucide-react';
import type { GraphNode, GraphRelationship } from '../../../lib/api';
import { ENTITY_TYPE_META } from './KnowledgeCanvas';

type KnowledgeNodePanelProps = {
  node: GraphNode;
  relationships: GraphRelationship[];
  candidates: GraphNode[];
  relationTypes: string[];
  onDeleteNode: () => void;
  onDeleteRelationship: (relationshipId: string) => void;
  onCreateRelationship: (targetId: string, relationType: string) => void;
};

export default function KnowledgeNodePanel({
  node,
  relationships,
  candidates,
  relationTypes,
  onDeleteNode,
  onDeleteRelationship,
  onCreateRelationship,
}: KnowledgeNodePanelProps) {
  const [targetId, setTargetId] = useState('');
  const [relationType, setRelationType] = useState('');
  const meta = ENTITY_TYPE_META[node.entity_type];
  const attributes = Object.entries(node.attributes);

  return (
    <aside className="control-panel knowledge-panel">
      <div className="panel-heading">
        <span>
          <span className="knowledge-type-badge" style={{ color: meta?.color, borderColor: meta?.color }}>
            {meta?.label ?? node.entity_type}
          </span>
        </span>
        <span className="muted">{node.is_canonical ? 'catálogo · somente leitura' : 'seu workspace'}</span>
      </div>
      <h2 className="knowledge-node-name">{node.name}</h2>
      {node.description && <p className="knowledge-node-description">{node.description}</p>}
      {node.external_ref && <p className="muted small">external ref: {node.external_ref}</p>}

      {attributes.length > 0 && (
        <table className="knowledge-attributes">
          <tbody>
            {attributes.map(([key, value]) => (
              <tr key={key}>
                <td>{key}</td>
                <td>{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="panel-heading knowledge-rel-heading">
        <span><ArrowLeftRight size={13} /> Relações ({relationships.length})</span>
      </div>
      {relationships.length === 0 ? (
        <p className="muted small">Sem relações ainda — ligue este nó a outro abaixo.</p>
      ) : (
        <ul className="knowledge-relation-list">
          {relationships.map(relationship => {
            const outgoing = relationship.source_id === node.id;
            const other = outgoing ? relationship.target : relationship.source;
            const label = outgoing ? relationship.display_label : relationship.reverse_relation_type;
            return (
              <li key={relationship.id} className="knowledge-relation-row">
                <span className="knowledge-relation-direction" data-direction={outgoing ? 'out' : 'in'}>
                  {outgoing ? '→' : '←'}
                </span>
                <span className="knowledge-relation-label">{label}</span>
                <span className="knowledge-relation-other">
                  {other.name}
                  <small>{other.entity_type}</small>
                </span>
                {!relationship.is_canonical && (
                  <button type="button" className="knowledge-relation-delete" title="Remover relação" onClick={() => onDeleteRelationship(relationship.id)}>
                    <Trash2 size={13} />
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <div className="panel-heading knowledge-link-heading">
        <span><Link2 size={13} /> Nova relação</span>
      </div>
      <div className="knowledge-link-form">
        <select value={relationType} onChange={event => setRelationType(event.target.value)}>
          <option value="">tipo de relação…</option>
          {relationTypes.map(type => <option key={type} value={type}>{type}</option>)}
        </select>
        <select value={targetId} onChange={event => setTargetId(event.target.value)}>
          <option value="">destino…</option>
          {candidates.map(candidate => <option key={candidate.id} value={candidate.id}>{candidate.name} · {candidate.entity_type}</option>)}
        </select>
        <button
          type="button"
          className="secondary-button"
          disabled={!relationType || !targetId || node.is_canonical}
          onClick={() => {
            if (!relationType || !targetId) return;
            onCreateRelationship(targetId, relationType);
            setTargetId('');
            setRelationType('');
          }}
        >
          <Link2 size={13} /> Ligar
        </button>
      </div>
      {node.is_canonical && <p className="muted small">Nós do catálogo são somente leitura — crie um nó próprio e relate-o ao catálogo.</p>}

      {!node.is_canonical && (
        <button type="button" className="secondary-button full knowledge-delete-node" onClick={onDeleteNode}>
          <Ban size={13} /> Remover nó
        </button>
      )}
    </aside>
  );
}
