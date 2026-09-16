import { defineConfig } from 'vitest/config';

// Frontend contract runner, deliberately scoped:
// PR004.1 covers Project Memory; PR006 covers the pure StoryboardState editor
// operations; V3.1 covers the pure Knowledge Graph layout helpers; PR009.2
// covers the fetch boundary through lib/api; V3.2.1 covers the network layer
// itself (lib/network) at a 98% floor. Visual composition is still guarded
// structurally by the backend suite and by `next build`.
export default defineConfig({
  test: {
    environment: 'node',
    include: [
      'lib/memory/**/*.test.ts',
      'lib/memory/**/*.test.tsx',
      'lib/storyboard/**/*.test.ts',
      'lib/graph/**/*.test.ts',
      'lib/api.network.test.ts',
      'lib/network/**/*.test.ts',
    ],
    coverage: {
      provider: 'v8',
      include: [
        'lib/memory/project_memory.ts',
        'lib/memory/use_project_memory.ts',
        'lib/storyboard/storyboard_state.ts',
        'lib/graph/layout.ts',
        'lib/network/**',
      ],
      // The spec's 95% floor, enforced (not just reported) — and the V3.2.1
      // network layer holds itself to 98: this module is the one that decides
      // what the user is told when things break.
      thresholds: {
        statements: 98,
        branches: 98,
        functions: 98,
        lines: 98,
      },
    },
  },
});
