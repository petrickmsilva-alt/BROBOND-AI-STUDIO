import { defineConfig } from 'vitest/config';

// Frontend contract runner, deliberately scoped:
// PR004.1 covers Project Memory; PR006 covers the pure StoryboardState editor
// operations; V3.1 covers the pure Knowledge Graph layout helpers; PR009.2
// covers the fetch boundary through lib/api; V3.2.1 covers the network layer
// itself (lib/network) at a 98% floor. PR012 (BROBOND UI 4.0) adds the design
// tokens/status-mapping helpers and the new presentational shell components
// (Sidebar, Hero Workspace, Storyboard Cards, Status Dock, Identity Bar) at
// the same 98% floor. Visual composition beyond these components is still
// guarded structurally by the backend suite and by `next build`.
export default defineConfig({
  // PR012 adds JSX-bearing component tests; `tsconfig.json` sets
  // `jsx: "preserve"` for Next.js's own compiler, but Vitest's esbuild
  // transform needs an explicit runtime to compile .tsx test files.
  esbuild: {
    jsx: 'automatic',
  },
  test: {
    environment: 'node',
    // PR012's component tests render with @testing-library/react across
    // multiple `it()` blocks in the same file; without `globals: true` its
    // automatic per-test `cleanup()` (registered via the global `afterEach`
    // hook) never runs, so later assertions in the same file see DOM nodes
    // left over from earlier renders. `globals: true` is exactly what
    // testing-library's auto-cleanup relies on — no other suite in this
    // repo needs it, so it costs nothing outside the new files.
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: [
      'lib/memory/**/*.test.ts',
      'lib/memory/**/*.test.tsx',
      'lib/storyboard/**/*.test.ts',
      'lib/graph/**/*.test.ts',
      'lib/api.network.test.ts',
      'lib/network/**/*.test.ts',
      'lib/theme/**/*.test.ts',
      'components/studio/sidebar.test.tsx',
      'components/studio/hero.test.tsx',
      'components/studio/storyboard_cards.test.tsx',
      'components/studio/status_dock.test.tsx',
      'components/studio/identity_bar.test.tsx',
    ],
    coverage: {
      provider: 'v8',
      include: [
        'lib/memory/project_memory.ts',
        'lib/memory/use_project_memory.ts',
        'lib/storyboard/storyboard_state.ts',
        'lib/graph/layout.ts',
        'lib/network/**',
        'lib/theme/tokens.ts',
        'lib/theme/status_mapping.ts',
        'components/studio/sidebar.tsx',
        'components/studio/hero-workspace.tsx',
        'components/studio/storyboard-cards.tsx',
        'components/studio/status-dock.tsx',
        'components/studio/identity-bar.tsx',
      ],
      // The spec's 95% floor, enforced (not just reported) — and the V3.2.1
      // network layer / PR012 UI 4.0 shell components hold themselves to
      // 98: these are the modules that decide what the user sees.
      thresholds: {
        statements: 98,
        branches: 98,
        functions: 98,
        lines: 98,
      },
    },
  },
});
