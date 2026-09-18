/**
 * BROBOND UI 4.0 — Cinematic Design System tokens.
 *
 * PR012 is UI/UX only: this module has zero runtime dependency on the
 * FastAPI backend, the Director/Storyboard/Quality engines, providers or
 * the database. It is the single source of truth for color, typography,
 * motion and layout constants consumed by `app/globals.css` (as CSS
 * custom properties) and by the presentational components under
 * `components/studio/*`.
 *
 * Rule of the palette: never pure white, never pure black. Every "white"
 * in the product is `#FAFAFA` (textPrimary) and every "black" is the
 * near-black `#07070A` background.
 */

/** Core color palette — luxury / cinematic / minimal / premium / dark. */
export const colors = {
  background: '#07070A',
  surface: '#111113',
  surface2: '#18181B',
  border: '#27272A',
  primary: '#8B5CF6',
  success: '#22C55E',
  warning: '#F59E0B',
  danger: '#EF4444',
  textPrimary: '#FAFAFA',
  textSecondary: '#A1A1AA',
} as const;

export type ColorToken = keyof typeof colors;

/** Typography hierarchy — Inter Variable, obligatory scale. */
export const typography = {
  displayXl: { name: 'Display XL', fontSize: '48px', fontWeight: 700, lineHeight: 1.05 },
  h1: { name: 'H1', fontSize: '34px', fontWeight: 700, lineHeight: 1.12 },
  h2: { name: 'H2', fontSize: '26px', fontWeight: 600, lineHeight: 1.18 },
  h3: { name: 'H3', fontSize: '20px', fontWeight: 600, lineHeight: 1.25 },
  body: { name: 'Body', fontSize: '15px', fontWeight: 400, lineHeight: 1.6 },
  caption: { name: 'Caption', fontSize: '12px', fontWeight: 500, lineHeight: 1.4 },
} as const;

export type TypographyToken = keyof typeof typography;

export const fontFamily = {
  sans: "'InterVariable', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  mono: "'DM Mono', ui-monospace, SFMono-Regular, monospace",
} as const;

/** Motion — subtle, never flashy. */
export const motion = {
  hoverDurationMs: 120,
  hoverEase: 'cubic-bezier(0.2, 0.8, 0.2, 1)',
  cardHoverScale: 1.01,
  sidebarFadeMs: 180,
  buttonElevation: '0 6px 18px rgba(139, 92, 246, 0.22)',
} as const;

/** Layout constants shared by the shell. */
export const layout = {
  sidebarWidth: 248,
  statusDockHeight: 52,
} as const;

/** Responsive breakpoints (max-width, px), per the DoD. */
export const breakpoints = {
  desktop: 1440,
  laptop: 1024,
  tablet: 768,
  mobile: 480,
} as const;

export type BreakpointToken = keyof typeof breakpoints;

/** Badges are the exception, not the rule — sidebar only shows these three. */
export const allowedBadges = ['GPU', 'SQL', 'AI'] as const;
export type AllowedBadge = (typeof allowedBadges)[number];

/**
 * Renders every token above as CSS custom properties so `globals.css` and
 * component styles share exactly one definition. Consumed once, at the
 * top of `:root` in `app/globals.css` (kept as a literal block there for
 * zero-JS first paint; this function exists for tooling / tests / any
 * future runtime theming needs).
 */
export function tokensToCssVariables(): Record<string, string> {
  return {
    '--bb-background': colors.background,
    '--bb-surface': colors.surface,
    '--bb-surface-2': colors.surface2,
    '--bb-border': colors.border,
    '--bb-primary': colors.primary,
    '--bb-success': colors.success,
    '--bb-warning': colors.warning,
    '--bb-danger': colors.danger,
    '--bb-text-primary': colors.textPrimary,
    '--bb-text-secondary': colors.textSecondary,
    '--bb-font-sans': fontFamily.sans,
    '--bb-font-mono': fontFamily.mono,
    '--bb-motion-hover': `${motion.hoverDurationMs}ms`,
    '--bb-motion-ease': motion.hoverEase,
    '--bb-sidebar-width': `${layout.sidebarWidth}px`,
    '--bb-status-dock-height': `${layout.statusDockHeight}px`,
  };
}

/** Status colors used by dynamic indicators (Status Dock, badges). */
export type IndicatorState = 'online' | 'degraded' | 'offline' | 'unknown';

export const indicatorColor: Record<IndicatorState, string> = {
  online: colors.success,
  degraded: colors.warning,
  offline: colors.danger,
  unknown: colors.textSecondary,
};

export function isAllowedBadge(value: string): value is AllowedBadge {
  return (allowedBadges as readonly string[]).includes(value);
}
