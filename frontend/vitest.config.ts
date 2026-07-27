import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

// Unit tests cover pure logic only — stores' reducers, lib helpers, color maps —
// so a plain node environment is enough (no jsdom). The task store imports the
// api/ws modules, but those touch `window` only inside functions, so importing
// them at module load is safe here.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
});
