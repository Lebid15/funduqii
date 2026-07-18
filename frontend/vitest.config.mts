import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/**
 * LIMITED frontend test runner (GUESTS-CLOSURE Decision 13). Vitest + React
 * Testing Library + jsdom for unit/component tests only — NO Playwright/E2E and
 * NO conversion of any existing tooling. The `@/` alias mirrors tsconfig's
 * `paths` mapping explicitly (baseUrl is unset in this project), so tests resolve
 * project modules the same way the app does without relying on a resolver plugin.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    css: false,
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
