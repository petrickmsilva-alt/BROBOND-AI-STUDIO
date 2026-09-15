import { defineConfig } from 'vitest/config';

// PR004.1 — the frontend contract test runner, deliberately scoped:
// behavioral tests cover the Project Memory contract (the Memory Adapter
// and its hook). The rest of the frontend is guarded structurally by the
// backend suite (test_frontend_honesty.py, test_studio_persona_pipeline.py,
// test_project_memory_contract.py).
export default defineConfig({
  test: {
    environment: 'node',
    include: ['lib/memory/**/*.test.ts', 'lib/memory/**/*.test.tsx'],
    coverage: {
      provider: 'v8',
      include: ['lib/memory/project_memory.ts', 'lib/memory/use_project_memory.ts'],
      // The spec's 95% floor, enforced (not just reported).
      thresholds: { statements: 95, branches: 95, functions: 95, lines: 95 },
    },
  },
});
