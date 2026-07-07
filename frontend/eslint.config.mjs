import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  {
    rules: {
      // The platform console fetches data on mount and resets modal forms when
      // they open — both are correct uses of effects to synchronize React with
      // an external system (the API / a freshly-opened dialog). This new
      // React-compiler heuristic flags those legitimate patterns at the call
      // site regardless of await-ordering, and the stack has no data-fetching
      // library to move them into. We relax it deliberately; all other
      // react-hooks rules (deps, rules-of-hooks) stay on.
      "react-hooks/set-state-in-effect": "off",
    },
  },
]);

export default eslintConfig;
