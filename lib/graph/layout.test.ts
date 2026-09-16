import { describe, expect, it } from 'vitest';
import {
  DEFAULT_NODE_COLOR,
  ENTITY_COLORS,
  colorForEntity,
  edgeMidpoint,
  edgePath,
  layoutRadial,
  truncateLabel,
} from './layout';

const NODES = [
  { id: 'c-ram', name: 'RAM 1500', entity_type: 'vehicle' },
  { id: 'c-pet', name: 'Petrick', entity_type: 'character' },
  { id: 'c-bro', name: 'BroBond', entity_type: 'brand' },
];

describe('colorForEntity', () => {
  it('maps every known entity type to its colour', () => {
    expect(colorForEntity('character')).toBe(ENTITY_COLORS.character);
    expect(colorForEntity('brand')).toBe(ENTITY_COLORS.brand);
    expect(colorForEntity('campaign')).toBe(ENTITY_COLORS.campaign);
    expect(colorForEntity('location')).toBe(ENTITY_COLORS.location);
    expect(colorForEntity('vehicle')).toBe(ENTITY_COLORS.vehicle);
    expect(colorForEntity('wardrobe')).toBe(ENTITY_COLORS.wardrobe);
    expect(colorForEntity('prop')).toBe(ENTITY_COLORS.prop);
  });

  it('falls back to the default colour for unknown types', () => {
    expect(colorForEntity('starship')).toBe(DEFAULT_NODE_COLOR);
    expect(colorForEntity('')).toBe(DEFAULT_NODE_COLOR);
  });
});

describe('layoutRadial', () => {
  it('returns no positions for an empty graph', () => {
    expect(layoutRadial([])).toEqual({});
  });

  it('pins a lone node at the canvas centre', () => {
    expect(layoutRadial([NODES[0]], { width: 800, height: 500 })).toEqual({
      'c-ram': { x: 400, y: 250 },
    });
  });

  it('centres the first node in sorted order and rings the rest from the top', () => {
    const positions = layoutRadial(NODES, { width: 800, height: 500 });
    // Sorted by name: BroBond, Petrick, RAM 1500. Ring radius = 250 * 0.72.
    expect(positions['c-bro']).toEqual({ x: 400, y: 250 });
    expect(positions['c-pet']).toEqual({ x: 400, y: 70 });
    expect(positions['c-ram']).toEqual({ x: 400, y: 430 });
  });

  it('honours an explicit centre id', () => {
    const positions = layoutRadial(NODES, { width: 800, height: 500, centerId: 'c-pet' });
    expect(positions['c-pet']).toEqual({ x: 400, y: 250 });
    expect(Object.keys(positions).sort()).toEqual(['c-bro', 'c-pet', 'c-ram']);
  });

  it('ignores an unknown centre id', () => {
    const positions = layoutRadial(NODES, { width: 800, height: 500, centerId: 'nope' });
    expect(positions['c-bro']).toEqual({ x: 400, y: 250 });
  });

  it('is deterministic regardless of input order', () => {
    expect(layoutRadial([...NODES].reverse())).toEqual(layoutRadial(NODES));
  });

  it('breaks name ties by id, deterministically', () => {
    const twins = [
      { id: 'n-b', name: 'Clone', entity_type: 'prop' },
      { id: 'n-a', name: 'Clone', entity_type: 'prop' },
    ];
    const positions = layoutRadial(twins, { width: 800, height: 500 });
    expect(positions['n-a']).toEqual({ x: 400, y: 250 });
    expect(positions['n-b']).toEqual({ x: 400, y: 70 });
  });

  it('keeps every node inside the canvas', () => {
    const many = Array.from({ length: 12 }, (_, i) => ({
      id: `n-${i}`,
      name: `Node ${String(i).padStart(2, '0')}`,
      entity_type: 'prop',
    }));
    const positions = layoutRadial(many, { width: 860, height: 520 });
    expect(Object.keys(positions)).toHaveLength(12);
    for (const point of Object.values(positions)) {
      expect(point.x).toBeGreaterThanOrEqual(0);
      expect(point.x).toBeLessThanOrEqual(860);
      expect(point.y).toBeGreaterThanOrEqual(0);
      expect(point.y).toBeLessThanOrEqual(520);
    }
  });
});

describe('edgePath', () => {
  it('connects two points with a straight segment', () => {
    expect(edgePath({ x: 400, y: 250 }, { x: 400, y: 70 })).toBe('M 400 250 L 400 70');
  });
});

describe('edgeMidpoint', () => {
  it('returns the centre of a connector', () => {
    expect(edgeMidpoint({ x: 400, y: 250 }, { x: 400, y: 70 })).toEqual({ x: 400, y: 160 });
  });
});

describe('truncateLabel', () => {
  it('keeps short names intact', () => {
    expect(truncateLabel('Petrick')).toBe('Petrick');
    expect(truncateLabel('123456789012345678')).toBe('123456789012345678');
  });

  it('shortens long names with an ellipsis', () => {
    expect(truncateLabel('Legacy Leather Jacket')).toBe('Legacy Leather Ja…');
    expect(truncateLabel('Legacy Leather Jacket')).toHaveLength(18);
  });
});
