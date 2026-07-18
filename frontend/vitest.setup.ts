// Vitest global setup (GUESTS-CLOSURE Decision 13). Registers the
// @testing-library/jest-dom matchers on Vitest's expect and auto-cleans the
// jsdom tree between tests. Loaded via `setupFiles` in vitest.config.mts.
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
