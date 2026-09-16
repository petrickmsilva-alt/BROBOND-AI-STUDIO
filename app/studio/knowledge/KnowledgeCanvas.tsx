'use client';

/**
 * V3.1 — the knowledge graph canvas.
 *
 * Deterministic layout, no external graph library: the seven entity types
 * form clusters arranged on a ring; the nodes of a cluster sit on a small
 * ring around their cluster label. Edges are quadratic curves with an arrow
 * on the target side and the relation label at the midpoint — the same label
 * the API ships (`display_label`), so what you read is what the graph stores.
 */
import { useMemo } from 'react';
import type { GraphNode, GraphNodeType, GraphRelationship } from '../../../lib/api';

export const ENTITY_TYPE_META: Record<GraphNodeType, { label: string; color: string }> = {
  character: { label: 'Character', color: '#a78bfa' },
  brand: { label: 'Brand', color: '#fbbf24' },
  campaign: { label: 'Campaign', color: '#f472b6' },
  location: { label: 'Location', color: '#38bdf8' },
  vehicle: { label: 'Vehicle', color: '#f87171' },
  wardrobe: { label: 'Wardrobe', color: '#34d399' },
  prop: { label: 'Prop', color: '#94a3b8' },
};

const ALL_TYPES = Object.keys(ENTITY_TYPE_META) as GraphNodeType[];
const VIEW_W = 1040;
const VIEW_H = 640;
const CENTER_X = VIEW_W / 2;
const CENTER_Y = VIEW_H / 2;
const RING_RADIUS = 225;
const CLUSTER_RADIUS = 74;

export type NodePosition = { x: number; y: number };

export function computeLayout(nodes: GraphNode[]): Map<string, NodePosition> {
  const positions = new Map<string, NodePosition>();
  const byType = new Map<GraphNodeType, GraphNode[]>();
  for (const type of ALL_TYPES) byType.set(type, []);
  for (const node of nodes) byType.get(node.entity_type)?.push(node);

  const clusters = ALL_TYPES.filter(type => (byType.get(type)?.length ?? 0) > 0);
  clusters.forEach((type, clusterIndex) => {
    const angle = (clusterIndex / clusters.length) * Math.PI * 2 - Math.PI / 2;
    const clusterX = CENTER_X + RING_RADIUS * Math.cos(angle);
    const clusterY = CENTER_Y + RING_RADIUS * Math.sin(angle);
    const members = byType.get(type) ?? [];
    if (members.length === 1) {
      positions.set(members[0].id, { x: clusterX, y: clusterY });
      return;
    }
    members.forEach((node, index) => {
      const memberAngle = (index / members.length) * Math.PI * 2 - Math.PI / 2;
      positions.set(node.id, {
        x: clusterX + CLUSTER_RADIUS * Math.cos(memberAngle),
        y: clusterY + CLUSTER_RADIUS * Math.sin(memberAngle),
      });
    });
  });
  return positions;
}

function edgePath(from: NodePosition, to: NodePosition) {
  const midX = (from.x + to.x) / 2;
  const midY = (from.y + to.y) / 2;
  // curve control point: push the midpoint toward the view center for a clean arc
  const controlX = midX + (CENTER_X - midX) * 0.18;
  const controlY = midY + (CENTER_Y - midY) * 0.18;
  return { d: `M ${from.x} ${from.y} Q ${controlX} ${controlY} ${to.x} ${to.y}`, midX: controlX, midY: controlY };
}

type KnowledgeCanvasProps = {
  nodes: GraphNode[];
  relationships: GraphRelationship[];
  selectedId: string | null;
  highlightIds: Set<string>;
  onSelect: (nodeId: string) => void;
};

export default function KnowledgeCanvas({ nodes, relationships, selectedId, highlightIds, onSelect }: KnowledgeCanvasProps) {
  const positions = useMemo(() => computeLayout(nodes), [nodes]);
  const nodeById = useMemo(() => new Map(nodes.map(node => [node.id, node])), [nodes]);
  const clusterLabels = useMemo(() => {
    const labels: { type: GraphNodeType; x: number; y: string }[] = [];
    const seen = new Set<GraphNodeType>();
    for (const node of nodes) {
      if (seen.has(node.entity_type)) continue;
      seen.add(node.entity_type);
      const siblings = nodes.filter(other => other.entity_type === node.entity_type);
      const siblingPositions = siblings.map(other => positions.get(other.id)).filter(Boolean) as NodePosition[];
      if (siblingPositions.length === 0) continue;
      const avgX = siblingPositions.reduce((sum, p) => sum + p.x, 0) / siblingPositions.length;
      const avgY = siblingPositions.reduce((sum, p) => sum + p.y, 0) / siblingPositions.length;
      labels.push({ type: node.entity_type, x: avgX, y: String(Math.max(12, avgY - CLUSTER_RADIUS - 18)) });
    }
    return labels;
  }, [nodes, positions]);

  return (
    <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} className="knowledge-canvas" role="img" aria-label="Knowledge graph">
      <defs>
        <marker id="knowledge-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" />
        </marker>
      </defs>

      {relationships.map(relationship => {
        const from = positions.get(relationship.source_id);
        const to = positions.get(relationship.target_id);
        if (!from || !to) return null;
        const { d, midX, midY } = edgePath(from, to);
        const dimmed = highlightIds.size > 0 && !highlightIds.has(relationship.source_id) && !highlightIds.has(relationship.target_id);
        const active = selectedId !== null && (relationship.source_id === selectedId || relationship.target_id === selectedId);
        return (
          <g key={relationship.id} opacity={dimmed ? 0.18 : 1} className="knowledge-edge">
            <path d={d} fill="none" stroke={active ? '#a78bfa' : '#64748b'} strokeWidth={active ? 2 : 1.2} markerEnd="url(#knowledge-arrow)" />
            <text x={midX} y={midY} textAnchor="middle" className={`knowledge-edge-label ${active ? 'active' : ''}`}>
              {relationship.display_label}
            </text>
          </g>
        );
      })}

      {clusterLabels.map(label => (
        <text key={label.type} x={label.x} y={label.y} textAnchor="middle" className="knowledge-cluster-label">
          {ENTITY_TYPE_META[label.type].label.toUpperCase()}
        </text>
      ))}

      {nodes.map(node => {
        const position = positions.get(node.id);
        if (!position) return null;
        const selected = selectedId === node.id;
        const dimmed = highlightIds.size > 0 && !highlightIds.has(node.id);
        const color = ENTITY_TYPE_META[node.entity_type]?.color ?? '#94a3b8';
        return (
          <g
            key={node.id}
            transform={`translate(${position.x}, ${position.y})`}
            className="knowledge-node"
            opacity={dimmed ? 0.25 : 1}
            onClick={() => onSelect(node.id)}
            role="button"
            aria-label={`${node.entity_type} ${node.name}`}
          >
            <circle r={selected ? 15 : 11} fill={color} opacity={node.is_canonical ? 1 : 0.55} stroke={selected ? '#f5f3ff' : '#0b0b12'} strokeWidth={selected ? 2.5 : 1.5} />
            {selected && <circle r={21} fill="none" stroke={color} strokeWidth={1} opacity={0.6} />}
            <text y={node.is_canonical ? -20 : -18} textAnchor="middle" className="knowledge-node-label">
              {node.name.length > 22 ? `${node.name.slice(0, 21)}…` : node.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
