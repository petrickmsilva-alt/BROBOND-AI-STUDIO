'use client';

/**
 * V3.4 — the radar chart over the measured criteria. Pure SVG: one axis per
 * criterion the report actually measured (unmeasured criteria are absent by
 * design — drawing them at zero would be inventing data), rings at 25/50/75/
 * 100, and the polygon of scores.
 */

import type { QualityCriterion } from '../../../lib/api';

const SIZE = 240;
const CENTER = SIZE / 2;
const RADIUS = 88;
const RING_LEVELS = [25, 50, 75, 100];
const LABEL_OFFSET = 16;
const MIN_AXES = 3;

function point(index: number, total: number, value: number): [number, number] {
  const angle = (Math.PI * 2 * index) / total - Math.PI / 2;
  const distance = (value / 100) * RADIUS;
  return [CENTER + Math.cos(angle) * distance, CENTER + Math.sin(angle) * distance];
}

export default function CriteriaRadar({
  criteria,
  labels,
}: {
  criteria: QualityCriterion[];
  labels: Record<string, string>;
}) {
  if (criteria.length < MIN_AXES) {
    return (
      <p className="quality-muted">
        Radar precisa de pelo menos {MIN_AXES} critérios medidos — este relatório tem {criteria.length}.
      </p>
    );
  }
  const total = criteria.length;
  const polygon = criteria
    .map((item, index) => point(index, total, item.score).join(','))
    .join(' ');
  return (
    <svg
      className="quality-radar"
      width={SIZE}
      height={SIZE}
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      role="img"
      aria-label={`Radar de ${total} critérios`}
    >
      {RING_LEVELS.map(level => (
        <polygon
          key={level}
          className="quality-radar-ring"
          points={criteria.map((_, index) => point(index, total, level).join(',')).join(' ')}
        />
      ))}
      {criteria.map((item, index) => {
        const [x, y] = point(index, total, 100);
        return <line key={item.criterion} className="quality-radar-axis" x1={CENTER} y1={CENTER} x2={x} y2={y} />;
      })}
      <polygon className="quality-radar-area" points={polygon} />
      {criteria.map((item, index) => {
        const [x, y] = point(index, total, item.score);
        return <circle key={item.criterion} className="quality-radar-dot" cx={x} cy={y} r={3} />;
      })}
      {criteria.map((item, index) => {
        const angle = (Math.PI * 2 * index) / total - Math.PI / 2;
        const x = CENTER + Math.cos(angle) * (RADIUS + LABEL_OFFSET);
        const y = CENTER + Math.sin(angle) * (RADIUS + LABEL_OFFSET);
        return (
          <text key={item.criterion} className="quality-radar-label" x={x} y={y} textAnchor="middle" dominantBaseline="central">
            {labels[item.criterion] ?? item.criterion}
          </text>
        );
      })}
    </svg>
  );
}
