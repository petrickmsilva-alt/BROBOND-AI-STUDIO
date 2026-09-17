'use client';

/**
 * V3.4 — the radial 0–100 score. Pure SVG, no chart dependency: the arc
 * length is the score fraction of the circumference, and the color follows
 * the decision band the backend already chose (the component never
 * re-derives thresholds — the status arrives with the report).
 */

const SIZE = 168;
const STROKE = 14;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

const BAND_COLORS: Record<string, string> = {
  retry: '#f87171',
  manual_review: '#fbbf24',
  approved: '#4ade80',
  masterpiece: '#c084fc',
};

const TRACK_COLOR = '#232128';
const FALLBACK_COLOR = '#88878b';

export default function ScoreRadial({ score, status }: { score: number; status: string }) {
  const bounded = Math.max(0, Math.min(100, score));
  const filled = (bounded / 100) * CIRCUMFERENCE;
  const color = BAND_COLORS[status] ?? FALLBACK_COLOR;
  return (
    <svg
      className="quality-score-radial"
      width={SIZE}
      height={SIZE}
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      role="img"
      aria-label={`Score ${bounded} de 100`}
    >
      <circle
        cx={SIZE / 2}
        cy={SIZE / 2}
        r={RADIUS}
        fill="none"
        stroke={TRACK_COLOR}
        strokeWidth={STROKE}
      />
      <circle
        cx={SIZE / 2}
        cy={SIZE / 2}
        r={RADIUS}
        fill="none"
        stroke={color}
        strokeWidth={STROKE}
        strokeLinecap="round"
        strokeDasharray={`${filled} ${CIRCUMFERENCE - filled}`}
        transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
      />
      <text x="50%" y="47%" textAnchor="middle" dominantBaseline="central" className="quality-score-number">
        {bounded}
      </text>
      <text x="50%" y="64%" textAnchor="middle" dominantBaseline="central" className="quality-score-caption">
        / 100
      </text>
    </svg>
  );
}
