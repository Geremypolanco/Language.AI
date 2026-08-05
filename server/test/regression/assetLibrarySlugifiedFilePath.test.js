// Regression test for a real bug found while building the Academic Asset
// Builder: persisted asset `file_path`s were built by re-slugifying the raw
// discipline/course/lesson strings a second time inline, instead of reading
// back the actual (already-slugified) directory names versionDir() wrote to
// on disk. Accented/spaced/uppercase lesson metadata (e.g. "Álgebra Lineal")
// produced a `file_path` that didn't match any real file — the fix (see
// AssetLibrary.js persistLessonVersion) derives it from the resolved
// absolute path instead. This pins that fix in place.
process.env.ASSET_LIBRARY_ROOT = 'test/tmp/regression-slugify';

import { test, describe, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import { persistLessonVersion } from '../../src/asset-builder/persistence/AssetLibrary.js';
import { libraryRoot } from '../../src/asset-builder/persistence/paths.js';

after(async () => {
  await fs.rm(libraryRoot(), { recursive: true, force: true });
});

describe('persistLessonVersion — file_path reflects the real, slugified directory names', () => {
  test('accented/spaced/uppercase discipline, course, and lesson names still produce a file_path pointing at a real file', async () => {
    const bytes = Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>', 'utf8');
    const checksum = crypto.createHash('sha256').update(bytes).digest('hex');

    const lesson = {
      discipline: 'Álgebra Lineal',
      courseId: 'Curso De Prueba',
      lessonId: 'Lección Uno',
      language: 'es',
    };
    const candidate = {
      provider: 'diagram-generator',
      resourceType: 'diagram',
      format: 'svg',
      license: 'proprietary-generated',
      bytes,
    };
    const validation = {
      checksum,
      scores: { quality: 0.9, educational: 0.9, relevance: 0.9 },
      dimensions: null,
    };

    const { assets } = await persistLessonVersion({
      lesson,
      resolvedAssets: [{ candidate, validation }],
      version: 1,
    });

    assert.equal(assets.length, 1);
    const filePath = assets[0].file_path;

    assert.ok(!/[A-ZÁ-Úáéíóúñ ]/.test(filePath), `file_path "${filePath}" contains unslugified characters`);
    assert.ok(
      filePath.startsWith('algebra-lineal/curso-de-prueba/leccion-uno/versions/v1/assets/diagrams/'),
      `file_path "${filePath}" does not match the real slugified directory layout`
    );

    const exists = await fs
      .access(`${libraryRoot()}/${filePath}`)
      .then(() => true)
      .catch(() => false);
    assert.equal(exists, true, 'the file_path must point at a file that actually exists on disk');
  });
});
