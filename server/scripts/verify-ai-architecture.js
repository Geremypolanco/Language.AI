#!/usr/bin/env node
// Structural sanity checks for the "AI architecture" (Academic Asset Builder
// provider chain, domain models, voice streaming, and the Express app's own
// boot path). Deliberately does NOT call any real AI provider or run a real
// model — the voice/LLM path uses the built-in dev-mock fallback (no
// AI_PROVIDER_API_KEY in CI), and the asset pipeline only exercises
// providers that need no network (local library, diagram generator, text
// extractor). This is meant to run on every CI push, so it has to stay fast
// and network-free — it is not a substitute for the full test suite.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { mkdtempSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';

// config/env.js is a module-level singleton evaluated on first import.
// ES module static imports are hoisted and evaluated before any of *this*
// file's own top-level code runs — so a static `import ... from
// '../src/utils/redisClient.js'` here would transitively load config/env.js
// (redisClient.js imports it directly) before the ASSET_LIBRARY_ROOT
// assignment below ever executes, freezing it at the wrong value. Every
// src/ import in this script must stay dynamic, after the assignment.
const tmpLibraryRoot = mkdtempSync(path.join(os.tmpdir(), 'ai-architecture-check-'));
process.env.ASSET_LIBRARY_ROOT = tmpLibraryRoot;

const steps = [];
function step(name, fn) {
  steps.push({ name, fn });
}

step('domain models instantiate and validate correctly', async () => {
  const { PublicationVersion, ValidationResult } = await import('../src/domain/editorial/index.js');
  const version = new PublicationVersion({ versionNumber: 1 });
  assert.equal(version.status.value, 'draft');
  const result = new ValidationResult({ check: 'smoke', passed: true });
  assert.equal(result.isBlocking(), false);
});

step('the asset provider priority chain registers every provider in spec order', async () => {
  const { createDefaultProviderChain } = await import('../src/asset-builder/providers/index.js');
  const chain = createDefaultProviderChain({ queryIndex: async () => [] });
  const names = chain.providers.map((p) => p.name);
  assert.deepEqual(names, [
    'local-library',
    'diagram-generator',
    'text-extractor',
    'open-educational-resources',
    'wikimedia-commons',
    'google-images',
    'ai-generation',
    'ai-tts',
  ]);
});

step('the asset-builder pipeline builds and persists a lesson with only network-free providers', async () => {
  const { buildLessonAssets } = await import('../src/asset-builder/pipeline/buildLessonAssets.js');

  const result = await buildLessonAssets(
    {
      lessonId: 'ai-architecture-smoke',
      courseId: 'smoke-course',
      discipline: 'Smoke Test',
      language: 'es',
      level: 'beginner',
      title: 'Prueba de arquitectura de IA',
      objectives: ['Verificar que el pipeline construye assets de forma consistente'],
      sections: [{ heading: 'Intro', body: 'Contenido mínimo para el smoke test del pipeline.' }],
    },
    { publish: true }
  );

  assert.equal(result.published, true);
  assert.ok(result.assets.length > 0, 'expected at least one asset to be built from network-free providers');
  for (const asset of result.assets) {
    const exists = await fs
      .access(path.join(tmpLibraryRoot, asset.file_path))
      .then(() => true)
      .catch(() => false);
    assert.ok(exists, `asset ${asset.id} reports file_path "${asset.file_path}" but no such file exists`);
  }
});

step('the voice reply stream initializes and streams via the dev-mock fallback (no provider credentials)', async () => {
  delete process.env.AI_PROVIDER_API_KEY;
  const { collectAiReply } = await import('../src/services/voice/streamingAiClient.js');
  const reply = await collectAiReply({
    systemPrompt: 'You are a helpful assistant.',
    messages: [{ role: 'user', content: 'hola' }],
  });
  assert.equal(typeof reply, 'string');
  assert.ok(reply.length > 0);
});

step('the Express app boots: every route module resolves and registers without throwing', async () => {
  const { createApp } = await import('../src/app.js');
  const app = createApp();
  assert.ok(typeof app.listen === 'function');
});

const results = [];
for (const { name, fn } of steps) {
  const startedAt = Date.now();
  try {
    await fn();
    results.push({ name, ok: true, ms: Date.now() - startedAt });
    console.log(`ok   ${name} (${Date.now() - startedAt}ms)`);
  } catch (err) {
    results.push({ name, ok: false, ms: Date.now() - startedAt, error: err });
    console.error(`FAIL ${name}`);
    console.error(err);
  }
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} AI-architecture checks passed.`);
if (failed.length > 0) {
  process.exitCode = 1;
}

await fs.rm(tmpLibraryRoot, { recursive: true, force: true });
// The Express-app-boot step opens the shared Redis connection used by the
// rate limiters; without closing it the socket keeps the event loop alive
// and this script never exits in CI. Dynamic import (not a static one at
// the top) so it can't drag config/env.js in before ASSET_LIBRARY_ROOT is set.
const { closeRedisClient } = await import('../src/utils/redisClient.js');
await closeRedisClient();
