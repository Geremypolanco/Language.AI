/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:4000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: false,
    include: ['src/**/*.test.{js,jsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'json-summary'],
      // Scoped to the pure-logic modules that actually have unit tests.
      // React components and the browser-API voice engine (mic/VAD/STT/TTS)
      // need jsdom+Testing Library or manual/e2e verification instead of a
      // coverage gate here — see the manual voice regression pass already
      // done for that surface. Widen this list as more modules get tests.
      include: [
        'src/utils/api.js',
        'src/voice/languageDetect.js',
        'src/voice/sentenceChunker.js',
        'src/voice/SessionManager.js',
        'src/voice/MemoryManager.js',
      ],
      thresholds: {
        lines: 95,
        statements: 95,
        functions: 95,
        branches: 90,
      },
    },
  },
});
