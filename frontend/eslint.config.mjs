import nextVitals from 'eslint-config-next/core-web-vitals'

const eslintConfig = [
  ...nextVitals,
  {
    // Default ignores of eslint-config-next.
    ignores: ['.next/**', 'out/**', 'build/**', 'next-env.d.ts'],
  },
  {
    // react-hooks v6 (bundled with eslint-config-next 16) turns on several new
    // rules that flag long-standing patterns in the animation layer — refs
    // mutated during render, client-only setState inside mount effects, etc.
    // Keep them visible as warnings instead of blocking CI or forcing risky
    // rewrites of the motion components; address as a dedicated cleanup later.
    rules: {
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/refs': 'warn',
      'react-hooks/static-components': 'warn',
      'react-hooks/purity': 'warn',
    },
  },
]

export default eslintConfig
