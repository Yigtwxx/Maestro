import nextVitals from 'eslint-config-next/core-web-vitals'

const eslintConfig = [
  ...nextVitals,
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
    rules: {
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/refs': 'warn',
      'react-hooks/static-components': 'warn',
      'react-hooks/purity': 'warn',
    },
  },
]

export default eslintConfig
