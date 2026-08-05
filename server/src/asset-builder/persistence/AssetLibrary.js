import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { randomUUID } from 'node:crypto';
import {
  lessonDir,
  versionDir,
  currentPointerPath,
  libraryRoot,
  assetSubfolderFor,
  assetFileName,
  ASSET_SUBFOLDERS,
} from './paths.js';
import { upsertLessonEntries } from './libraryIndex.js';
import { AssetMetadata, AssetManifest } from '../../domain/editorial/index.js';

/**
 * The permanent, versioned educational asset library described in the spec:
 *
 *   academy/<discipline>/<course>/<lesson>/
 *     current.json              <- pointer to the published version
 *     versions/
 *       v1/ content.json, metadata.json, assets/{images,videos,audio,diagrams,illustrations}/
 *       v2/ ...
 *
 * Building a new version never touches any other lesson's directory or the
 * shared index until publishVersion() runs — so re-building one lesson's
 * assets is exactly that: one lesson, not a whole-library rebuild.
 */

export async function getCurrentVersion(discipline, courseId, lessonId) {
  try {
    const raw = await fs.readFile(currentPointerPath(discipline, courseId, lessonId), 'utf8');
    return JSON.parse(raw).version;
  } catch (err) {
    if (err.code === 'ENOENT') return null;
    throw err;
  }
}

export async function getNextVersionNumber(discipline, courseId, lessonId) {
  const current = await getCurrentVersion(discipline, courseId, lessonId);
  return (current || 0) + 1;
}

export async function listVersions(discipline, courseId, lessonId) {
  const dir = path.join(lessonDir(discipline, courseId, lessonId), 'versions');
  try {
    const entries = await fs.readdir(dir);
    return entries
      .filter((e) => /^v\d+$/.test(e))
      .map((e) => Number(e.slice(1)))
      .sort((a, b) => a - b);
  } catch (err) {
    if (err.code === 'ENOENT') return [];
    throw err;
  }
}

/**
 * Writes one lesson version's content + resolved assets to disk. Deliberately
 * does NOT update the "current" pointer or the shared reuse index — that's
 * publishVersion()'s job, keeping Persistence and Publication as distinct
 * pipeline steps (a version can be built and inspected before it goes live).
 */
export async function persistLessonVersion({ lesson, resolvedAssets, version }) {
  const { discipline, courseId, lessonId, language } = lesson;
  const dir = versionDir(discipline, courseId, lessonId, version);

  await fs.mkdir(dir, { recursive: true });
  for (const sub of ASSET_SUBFOLDERS) await fs.mkdir(path.join(dir, 'assets', sub), { recursive: true });

  const now = new Date().toISOString();
  const assetMetadataList = [];

  for (const resolved of resolvedAssets) {
    const { candidate, validation } = resolved;
    const assetId = randomUUID();
    const subfolder = assetSubfolderFor(candidate.resourceType);
    const fileName = assetFileName(assetId, candidate.format);
    const relativeFilePath = subfolder === '.' ? fileName : path.join('assets', subfolder, fileName);
    const absoluteFilePath = path.join(dir, relativeFilePath);

    let checksum = validation.checksum;
    if (candidate.bytes) {
      await fs.writeFile(absoluteFilePath, candidate.bytes);
    } else if (candidate.filePath) {
      // Reused from elsewhere in the library — copy it into this version instead of refetching.
      const sourcePath = path.join(libraryRoot(), candidate.filePath);
      await fs.copyFile(sourcePath, absoluteFilePath);
      if (!checksum) {
        checksum = crypto.createHash('sha256').update(await fs.readFile(absoluteFilePath)).digest('hex');
      }
    } else {
      continue; // validator requires bytes or filePath — this shouldn't happen
    }

    // Derived from the actual (slugified) absolute path rather than rebuilt
    // from the raw discipline/course/lesson strings — those may contain
    // spaces/accents/uppercase that don't match the real directory names
    // versionDir() creates on disk (e.g. "Álgebra Lineal" -> "algebra-lineal").
    const libraryRelativePath = path.relative(libraryRoot(), absoluteFilePath).split(path.sep).join('/');

    const metadata = new AssetMetadata({
      id: assetId,
      lesson_id: lessonId,
      course_id: courseId,
      language,
      resource_type: candidate.resourceType,
      provider: candidate.provider,
      version,
      license: candidate.license,
      keywords: candidate.keywords || [],
      created_at: now,
      updated_at: now,
      quality_score: validation.scores.quality,
      educational_score: validation.scores.educational,
      format: candidate.format,
      file_path: libraryRelativePath,
      source_url: candidate.sourceUrl,
      width: validation.dimensions?.width,
      height: validation.dimensions?.height,
      duration_seconds: candidate.duration_seconds,
      checksum_sha256: checksum,
      relevance_score: validation.scores.relevance,
    });

    assetMetadataList.push(metadata);
  }

  const manifest = new AssetManifest({ lessonId, courseId, discipline, language, version, builtAt: now, assets: assetMetadataList });

  await fs.writeFile(path.join(dir, 'content.json'), JSON.stringify(lesson, null, 2), 'utf8');
  await fs.writeFile(path.join(dir, 'metadata.json'), JSON.stringify(manifest, null, 2), 'utf8');

  return { dir, assets: assetMetadataList, manifest };
}

/** Makes a built version the one students are served, and adds its assets to the reuse index. */
export async function publishVersion(discipline, courseId, lessonId, version) {
  const dir = lessonDir(discipline, courseId, lessonId);
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(
    currentPointerPath(discipline, courseId, lessonId),
    JSON.stringify({ version, publishedAt: new Date().toISOString() }, null, 2),
    'utf8'
  );

  const metaPath = path.join(versionDir(discipline, courseId, lessonId, version), 'metadata.json');
  const meta = JSON.parse(await fs.readFile(metaPath, 'utf8'));
  await upsertLessonEntries(lessonId, meta.assets);
}

/** Read-path used by the (read-only) student-facing serving routes. */
export async function readCurrentLesson(discipline, courseId, lessonId) {
  const version = await getCurrentVersion(discipline, courseId, lessonId);
  if (!version) return null;
  const dir = versionDir(discipline, courseId, lessonId, version);
  const [content, metadata] = await Promise.all([
    fs.readFile(path.join(dir, 'content.json'), 'utf8').then(JSON.parse),
    fs.readFile(path.join(dir, 'metadata.json'), 'utf8').then(JSON.parse),
  ]);
  return { version, content, metadata };
}

/**
 * Overwrites one already-persisted asset's file + metadata in place — the
 * targeted repair the maintenance job uses so fixing a broken link touches
 * exactly one asset, not the lesson's other resources or its version history.
 */
export async function replaceAssetInVersion(discipline, courseId, lessonId, version, assetId, { candidate, validation }) {
  const dir = versionDir(discipline, courseId, lessonId, version);
  const metaPath = path.join(dir, 'metadata.json');
  const meta = JSON.parse(await fs.readFile(metaPath, 'utf8'));
  const idx = meta.assets.findIndex((a) => a.id === assetId);
  if (idx === -1) throw new Error(`Asset ${assetId} not found in lesson ${lessonId} v${version}`);

  const existing = meta.assets[idx];
  const absoluteFilePath = path.join(libraryRoot(), existing.file_path);

  if (candidate.bytes) {
    await fs.writeFile(absoluteFilePath, candidate.bytes);
  } else if (candidate.filePath) {
    await fs.copyFile(path.join(libraryRoot(), candidate.filePath), absoluteFilePath);
  }

  const checksum =
    validation.checksum ||
    (candidate.bytes ? crypto.createHash('sha256').update(candidate.bytes).digest('hex') : existing.checksum_sha256);

  const updated = new AssetMetadata({
    ...existing,
    provider: candidate.provider,
    license: candidate.license,
    updated_at: new Date().toISOString(),
    quality_score: validation.scores.quality,
    educational_score: validation.scores.educational,
    relevance_score: validation.scores.relevance,
    width: validation.dimensions?.width ?? existing.width,
    height: validation.dimensions?.height ?? existing.height,
    checksum_sha256: checksum,
    source_url: candidate.sourceUrl ?? existing.source_url,
  });

  const manifest = new AssetManifest({
    ...meta,
    assets: meta.assets.map((a, i) => (i === idx ? updated : new AssetMetadata(a))),
  });
  await fs.writeFile(metaPath, JSON.stringify(manifest, null, 2), 'utf8');
  return { updated, allAssets: manifest.assets };
}

/** Resolves a requested asset file to an absolute path, refusing anything outside the published version's directory. */
export async function resolveAssetFilePath(discipline, courseId, lessonId, relativeAssetPath) {
  const version = await getCurrentVersion(discipline, courseId, lessonId);
  if (!version) return null;
  const dir = versionDir(discipline, courseId, lessonId, version);
  const target = path.join(dir, relativeAssetPath);
  if (target !== dir && !target.startsWith(dir + path.sep)) return null; // path traversal guard
  try {
    await fs.access(target);
    return target;
  } catch {
    return null;
  }
}
