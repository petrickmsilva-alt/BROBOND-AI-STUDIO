// PR012 — jsdom matcher setup for the new component tests
// (sidebar/hero/storyboard-cards/status-dock/identity-bar). Every other
// suite in the repo runs under `environment: 'node'` with plain
// assertions; this file only affects specs that opt into
// `@vitest-environment jsdom` and use `@testing-library/jest-dom`
// matchers (`toBeInTheDocument`, `toHaveAttribute`, `toHaveClass`, ...).
import '@testing-library/jest-dom/vitest';
