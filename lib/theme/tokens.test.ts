import { describe, expect, it } from 'vitest';
import {
  allowedBadges,
  breakpoints,
  colors,
  fontFamily,
  indicatorColor,
  isAllowedBadge,
  layout,
  motion,
  tokensToCssVariables,
  typography,
} from './tokens';

describe('design tokens', () => {
  it('never uses pure white or pure black for text/background roles', () => {
    const roles = [colors.background, colors.textPrimary, colors.surface, colors.surface2];
    for (const value of roles) {
      expect(value.toLowerCase()).not.toBe('#ffffff');
      expect(value.toLowerCase()).not.toBe('#000000');
    }
  });

  it('exposes the exact palette required by PR012', () => {
    expect(colors).toEqual({
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
    });
  });

  it('exposes the required typography hierarchy', () => {
    expect(typography.displayXl.fontSize).toBe('48px');
    expect(typography.h1.fontSize).toBe('34px');
    expect(typography.h2.fontSize).toBe('26px');
    expect(typography.h3.fontSize).toBe('20px');
    expect(typography.body.fontSize).toBe('15px');
    expect(typography.caption.fontSize).toBe('12px');
    expect(typography.displayXl.fontWeight).toBe(700);
    expect(typography.body.fontWeight).toBe(400);
  });

  it('uses Inter Variable as the primary font', () => {
    expect(fontFamily.sans).toContain('InterVariable');
  });

  it('fixes the sidebar width at 248px and the status dock at 52px', () => {
    expect(layout.sidebarWidth).toBe(248);
    expect(layout.statusDockHeight).toBe(52);
  });

  it('defines the required responsive breakpoints', () => {
    expect(breakpoints).toEqual({ desktop: 1440, laptop: 1024, tablet: 768, mobile: 480 });
  });

  it('keeps motion subtle: 120ms hover and 1.01 card scale', () => {
    expect(motion.hoverDurationMs).toBe(120);
    expect(motion.cardHoverScale).toBe(1.01);
  });

  it('serializes every token to a CSS custom property', () => {
    const vars = tokensToCssVariables();
    expect(vars['--bb-background']).toBe(colors.background);
    expect(vars['--bb-primary']).toBe(colors.primary);
    expect(vars['--bb-sidebar-width']).toBe('248px');
    expect(vars['--bb-status-dock-height']).toBe('52px');
    expect(vars['--bb-motion-hover']).toBe('120ms');
  });

  it('maps indicator states to the right semantic color', () => {
    expect(indicatorColor.online).toBe(colors.success);
    expect(indicatorColor.degraded).toBe(colors.warning);
    expect(indicatorColor.offline).toBe(colors.danger);
    expect(indicatorColor.unknown).toBe(colors.textSecondary);
  });

  it('restricts sidebar badges to GPU, SQL and AI', () => {
    expect(allowedBadges).toEqual(['GPU', 'SQL', 'AI']);
    expect(isAllowedBadge('GPU')).toBe(true);
    expect(isAllowedBadge('SQL')).toBe(true);
    expect(isAllowedBadge('AI')).toBe(true);
    expect(isAllowedBadge('NEW')).toBe(false);
    expect(isAllowedBadge('CORE')).toBe(false);
    expect(isAllowedBadge('')).toBe(false);
  });
});
