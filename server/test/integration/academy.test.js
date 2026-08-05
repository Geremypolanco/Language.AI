import { test, describe, before, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { startTestServer, stopTestServer } from './helpers/testServer.js';
import { buildLessonAssets } from '../../src/asset-builder/pipeline/buildLessonAssets.js';
import { libraryRoot } from '../../src/asset-builder/persistence/paths.js';

// Requires ASSET_LIBRARY_ROOT to point at a disposable temp directory — see
// the "test:integration" script in package.json. This suite builds a real
// lesson through the real Academic Asset Builder pipeline, then verifies
// the read-only serving routes against what was actually persisted.

let server;
let baseUrl;
let built;

const testLesson = {
  lessonId: 'integration-test-lesson',
  courseId: 'integration-course',
  discipline: 'Álgebra Lineal',
  language: 'es',
  level: 'beginner',
  title: 'Lección de prueba de integración',
  objectives: ['Resolver ecuaciones lineales'],
  sections: [{ heading: 'Intro', body: 'Una ecuación lineal tiene la forma 3x + 5 = 20.' }],
};

before(async () => {
  ({ server, baseUrl } = await startTestServer());
  built = await buildLessonAssets(testLesson, { publish: true });
});

after(async () => {
  await stopTestServer(server);
  await fs.rm(libraryRoot(), { recursive: true, force: true });
});

describe('GET /api/academy/:discipline/:course/:lesson', () => {
  test('serves the real published lesson content and metadata', async () => {
    const res = await fetch(`${baseUrl}/api/academy/algebra-lineal/integration-course/integration-test-lesson`);
    assert.equal(res.status, 200);
    const body = await res.json();
    assert.equal(body.version, built.version);
    assert.equal(body.content.title, testLesson.title);
    assert.equal(body.metadata.assets.length, built.assets.length);
  });

  test('returns 404 for a lesson that was never built', async () => {
    const res = await fetch(`${baseUrl}/api/academy/nope/nope/nope`);
    assert.equal(res.status, 404);
  });
});

describe('GET /api/academy/file/*', () => {
  test('serves a real persisted asset file with the right content-type', async () => {
    const asset = built.assets[0];
    const res = await fetch(`${baseUrl}/api/academy/file/${asset.file_path}`);
    assert.equal(res.status, 200);
    const bytes = await res.arrayBuffer();
    assert.ok(bytes.byteLength > 0);
  });

  test('rejects path traversal attempts', async () => {
    const res = await fetch(
      `${baseUrl}/api/academy/file/algebra-lineal/integration-course/integration-test-lesson/versions/v1/%2e%2e/%2e%2e/etc/passwd`
    );
    assert.equal(res.status, 400);
  });

  test('refuses to serve a version that is not the currently published one', async () => {
    const asset = built.assets[0];
    const fakeOldVersionPath = asset.file_path.replace(`v${built.version}`, 'v999');
    const res = await fetch(`${baseUrl}/api/academy/file/${fakeOldVersionPath}`);
    assert.equal(res.status, 404);
  });

  test('returns 404 for a file that does not exist within a real, current version directory', async () => {
    const res = await fetch(
      `${baseUrl}/api/academy/file/algebra-lineal/integration-course/integration-test-lesson/versions/v${built.version}/assets/diagrams/does-not-exist.svg`
    );
    assert.equal(res.status, 404);
  });
});

describe('Rebuilding a lesson creates an isolated new version', () => {
  test('a second build increments the version and republishes without touching version 1 on disk', async () => {
    const rebuilt = await buildLessonAssets(testLesson, { publish: true });
    assert.equal(rebuilt.version, built.version + 1);

    const v1Dir = path.join(path.dirname(built.directory), `v${built.version}`);
    const stillExists = await fs
      .access(v1Dir)
      .then(() => true)
      .catch(() => false);
    assert.equal(stillExists, true, 'the original version directory must not be deleted by a rebuild');
  });
});
