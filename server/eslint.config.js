import js from '@eslint/js';
import globals from 'globals';

/**
 * Flat ESLint config for the Express backend. Node globals only — this
 * package never runs in a browser. Kept intentionally close to
 * `eslint:recommended` plus a small set of high-value rules (no-unused-vars
 * as an error, not a warning, so CI actually gates on it) rather than a
 * large opinionated ruleset that would mostly just create churn.
 */
export default [
  js.configs.recommended,
  {
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'module',
      globals: { ...globals.node },
    },
    rules: {
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      'no-console': 'off', // this service logs operationally to stdout/stderr by design
      eqeqeq: ['error', 'smart'],
      'no-var': 'error',
      'prefer-const': 'error',
    },
  },
  {
    ignores: ['node_modules/', 'academy/', 'test/fixtures/', 'test/tmp/', 'coverage/'],
  },
];
