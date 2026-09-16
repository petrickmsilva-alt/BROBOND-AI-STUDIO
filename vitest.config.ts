import { defineConfig } from 'vitest/config';

// Frontend contract runner, deliberately scoped:
// PR004.1 covers Project Memory; PR006 covers the pure StoryboardState editor
// operations. Visual composition is still guarded structurally by the backend
// suite and by `next build`.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['lib/memory/**/*.test.ts', 'lib/memory/**/*.test.tsx', 'lib/storyboard/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      include: ['lib/memory/project_memory.ts', 'lib/memory/use_project_memory.ts', 'lib/storyboard/storyboard_state.ts'],
      // The spec's 95% floor, enforced (not just reported).
      thresholds: { statements: 95, branches: 95, functions: 95, lines: 95 },
    },
  },
});
