import nextVitals from 'eslint-config-next/core-web-vitals'
import nextTypescript from 'eslint-config-next/typescript'

const eslintConfig = [
  ...nextVitals,
  // typescript-eslint's `recommended` set. This is what makes
  // `@typescript-eslint/no-explicit-any` an *error*, and it is the only gate
  // that catches an `any`: `tsc --noEmit` accepts one by definition, so
  // without this config a hand-written `any` passed every check silently.
  // `recommended` needs no type information, so it does not pull in the
  // type-checked mode the policy note below rules out.
  ...nextTypescript,
  {
    // Default ignores of eslint-config-next.
    ignores: ['.next/**', 'out/**', 'build/**', 'next-env.d.ts'],
  },
  {
    // react-hooks v6/v7 (bundled with eslint-config-next 16) turns on several
    // new rules that flag long-standing patterns in the animation layer — refs
    // mutated during render, client-only setState inside mount effects, etc.
    // Keep them visible as warnings instead of blocking CI or forcing risky
    // rewrites of the motion components; address as a dedicated cleanup later.
    //
    // Policy (deliberate, do not "tighten" without auditing the fallout):
    // these fire on CORRECT code — `set-state-in-effect` on the canonical
    // fetch-then-setState data-loading pattern, `refs`/`purity` on intentional
    // imperative canvas/animation code — so promoting them to `error`, or
    // running `eslint` with `--max-warnings=0`, would fail CI on correct code.
    // `next build` also treats warnings as non-fatal. Type-aware linting is
    // intentionally NOT enabled; `tsc --noEmit` (the `type-check` gate) covers
    // type correctness deterministically without the flakiness of typed rules.
    // This demotion applies only to these four rules — the typescript-eslint
    // set spread in above stays at its own severities.
    rules: {
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/refs': 'warn',
      'react-hooks/static-components': 'warn',
      'react-hooks/purity': 'warn',
    },
  },
]

export default eslintConfig
