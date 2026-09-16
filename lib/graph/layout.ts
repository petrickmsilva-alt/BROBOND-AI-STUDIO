/**
 * V3.1 — Cinematic Knowledge Graph: deterministic SVG layout helpers.
 *
 * Pure functions only (no DOM, no fetch): radial placement, edge paths,
 * entity colours and label truncation. The Knowledge page renders whatever
 * these return, so every behaviour here is pinned by `layout.test.ts`.
 */

export interface LayoutNode {
  id: string;
  name: string;
  entity_type: string;
}

export interface LayoutEdge {
  source_id: string;
  target_id: string;
  relation: string;
}

export interface Point {
  x: number;
  y: number;
}

export const ENTITY_COLORS: Record<string, string> = {
  brand: '#78c6ff',
  campaign: '#f472b6',
  character: '#a98aff',
  location: '#73dfa3',
  prop: '#8a929b',
  vehicle: '#e8cf9a',
  wardrobe: '#e0a458',
};

export const DEFAULT_NODE_COLOR = '#8a929b';

export function colorForEntity(entityType: string): string {
  return ENTITY_COLORS[entityType] ?? DEFAULT_NODE_COLOR;
}

export interface RadialLayoutOptions {
  width?: number;
  height?: number;
  /** Node pinned at the centre; defaults to the first node in sorted order. */
  centerId?: string | null;
  /** Ring radius as a fraction of half the smaller canvas side (0–1). */
  radiusRatio?: number;
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

function sortNodes(nodes: LayoutNode[]): LayoutNode[] {
  return [...nodes].sort(
    (a, b) => a.name.localeCompare(b.name, 'en') || a.id.localeCompare(b.id),
  );
}

/**
 * Deterministic radial layout: one node at the centre, the rest spread
 * evenly on a ring starting at the top. Input order never matters — nodes
 * are sorted by (name, id) first — so re-renders don't make nodes jump.
 */
export function layoutRadial(
  nodes: LayoutNode[],
  options: RadialLayoutOptions = {},
): Record<string, Point> {
  const width = options.width ?? 800;
  const height = options.height ?? 500;
  const cx = round1(width / 2);
  const cy = round1(height / 2);
  const ordered = sortNodes(nodes);
  if (ordered.length === 0) return {};
  const ratio = Math.min(Math.max(options.radiusRatio ?? 0.72, 0), 1);
  const radius = round1((Math.min(width, height) / 2) * ratio);

  const requested = options.centerId
    ? ordered.find(node => node.id === options.centerId)
    : undefined;
  const center = requested ?? ordered[0];
  const ring = ordered.filter(node => node.id !== center.id);
  const positions: Record<string, Point> = { [center.id]: { x: cx, y: cy } };
  ring.forEach((node, index) => {
    const angle = -Math.PI / 2 + (index / ring.length) * Math.PI * 2;
    positions[node.id] = {
      x: round1(cx + radius * Math.cos(angle)),
      y: round1(cy + radius * Math.sin(angle)),
    };
  });
  return positions;
}

/** Straight connector path between two laid-out points. */
export function edgePath(from: Point, to: Point): string {
  return `M ${from.x} ${from.y} L ${to.x} ${to.y}`;
}

/** Midpoint of a connector, where the relation label sits. */
export function edgeMidpoint(from: Point, to: Point): Point {
  return { x: round1((from.x + to.x) / 2), y: round1((from.y + to.y) / 2) };
}

/** Shorten long node names for the canvas; the full name stays in `<title>`. */
export function truncateLabel(name: string, max = 18): string {
  if (name.length <= max) return name;
  return `${name.slice(0, max - 1)}…`;
}
