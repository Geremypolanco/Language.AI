import { Router } from 'express';
import path from 'node:path';
import fs from 'node:fs/promises';
import { readCurrentLesson, getCurrentVersion } from '../asset-builder/persistence/AssetLibrary.js';
import { libraryRoot } from '../asset-builder/persistence/paths.js';

export const academyRouter = Router();

/**
 * Strictly read-only surface over the Academic Asset Builder's persisted
 * library. Every handler here is a filesystem read of content the pipeline
 * already built and published — nothing on this router ever searches,
 * fetches from a third party, or generates a resource. That guarantee is
 * what keeps a lesson load O(1) filesystem reads regardless of how large
 * the catalog grows.
 */

academyRouter.get('/:discipline/:course/:lesson', async (req, res) => {
  const { discipline, course, lesson } = req.params;
  const result = await readCurrentLesson(discipline, course, lesson).catch(() => null);
  if (!result) {
    return res.status(404).json({ error: 'lesson_not_found', message: 'No published version exists for this lesson.' });
  }
  res.json(result);
});

/**
 * Serves one asset file by the exact `file_path` its metadata carries
 * (<discipline>/<course>/<lesson>/versions/v<N>/...). Only ever serves the
 * *currently published* version for that lesson — a superseded or
 * not-yet-published draft version is never reachable here, even if you know
 * its path, so a mid-rebuild lesson can't leak an inconsistent state to
 * students.
 */
academyRouter.get('/file/*', async (req, res) => {
  const relativePath = req.params[0];
  if (!relativePath || relativePath.includes('..')) {
    return res.status(400).json({ error: 'invalid_path' });
  }

  const [disciplineSlug, courseSlug, lessonSlug, versionsLiteral, versionSegment] = relativePath.split('/');
  if (versionsLiteral !== 'versions' || !/^v\d+$/.test(versionSegment || '')) {
    return res.status(400).json({ error: 'invalid_path' });
  }

  const currentVersion = await getCurrentVersion(disciplineSlug, courseSlug, lessonSlug).catch(() => null);
  if (!currentVersion || `v${currentVersion}` !== versionSegment) {
    return res.status(404).json({ error: 'asset_not_found' });
  }

  const root = libraryRoot();
  const absolutePath = path.join(root, relativePath);
  if (absolutePath !== root && !absolutePath.startsWith(root + path.sep)) {
    return res.status(400).json({ error: 'invalid_path' });
  }

  try {
    await fs.access(absolutePath);
  } catch {
    return res.status(404).json({ error: 'asset_not_found' });
  }

  // Moderate cache, not "immutable": the maintenance job can overwrite a
  // broken asset's bytes in place at this same path during a repair.
  res.set('Cache-Control', 'public, max-age=3600');
  res.sendFile(absolutePath);
});
