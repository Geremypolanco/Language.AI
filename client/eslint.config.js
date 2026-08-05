import js from '@eslint/js';
import globals from 'globals';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';

/** Flat ESLint config for the React/Vite frontend — browser globals, JSX, and the Hooks rules that actually catch real bugs (deps arrays, conditional hooks). */
export default [
  js.configs.recommended,
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'module',
      globals: { ...globals.browser },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      react,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...react.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      'react/react-in-jsx-scope': 'off', // React 17+ automatic JSX runtime
      'react/prop-types': 'off', // this codebase doesn't use prop-types; Zod validates at the API boundary instead
      'react-refresh/only-export-components': 'warn',
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      'no-var': 'error',
      'prefer-const': 'error',
    },
    settings: {
      react: { version: 'detect' },
    },
  },
  {
    ignores: ['node_modules/', 'dist/', 'coverage/'],
  },
];
