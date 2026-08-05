import fs from 'node:fs/promises';
import path from 'node:path';
import { libraryRoot } from '../persistence/paths.js';
import { getCurrentVersion, readCurrentLesson, replaceAssetInVersion } from '../persistence/AssetLibrary.js';
import {
  getAllEntries,
  upsertLessonEntries,
  queryIndex,
  isDuplicateChecksumExcluding,
} from '../persistence/libraryIndex.js';
import { createDefaultProviderChain } from '../providers/index.js';
import { createAssetValidator } from '../validation/AssetValidator.js';
import { analyzeLesson } from '../analyzer/AssetAnalyzer.js';
import { planLessonAssets } from '../planner/AssetPlanner.js';

/**
 * Standalone maintenance job: sweeps the published library for broken links
 * and missing files, and replaces only the affected assets. This is never
 * imported by the Express app or run during a student's session — it's
 * meant to be invoked by an external scheduler (cron, a Routine, etc.) via
 * `npm run assets:maintain` (see scripts/run-asset-maintenance.js).
 */

async function isReachable(entry, timeoutMs) {
  if (entry.source_url) {
    try {
      const res = await fetch(entry.source_url, { method: 'HEAD', signal: AbortSignal.timeout(timeoutMs) });
      return res.ok;
    } catch {
      return false;
    }
  }
  try {
    await fs.access(path.join(libraryRoot(), entry.file_path));
    return true;
  } catch {
    return false;
  }
}

/**
 * The entry's own file_path already carries slugified <discipline>/<course>/
 * <lesson> segments (see AssetLibrary.persistLessonVersion), so these are
 * safe to reuse directly as path args to the persistence layer.
 */
function pathSegmentsFromEntry(entry) {
  const [disciplineSlug, courseSlug, lessonSlug] = entry.file_path.split('/');
  return { disciplineSlug, courseSlug, lessonSlug };
}

/**
 * A regenerated replacement can legitimately come out byte-identical to the
 * asset it's replacing (e.g. TextResourceProvider deterministically
 * re-extracting the same excerpts) — that must not be flagged as a
 * duplicate of itself just because the index hasn't been updated yet.
 */
function duplicateCheckExcluding(excludeId) {
  return (checksum) => isDuplicateChecksumExcluding(checksum, excludeId);
}

export async function runMaintenance({ timeoutMs = 8000 } = {}) {
  const entries = await getAllEntries();
  const chain = createDefaultProviderChain({ queryIndex });

  const report = { checked: 0, broken: [], replaced: [], stillBroken: [] };

  for (const entry of entries) {
    report.checked += 1;
    if (await isReachable(entry, timeoutMs)) continue;

    report.broken.push(entry.id);
    console.warn(
      `[asset-maintenance] broken asset detected: ${entry.id} (${entry.resource_type}, lesson ${entry.lesson_id})`
    );

    const { disciplineSlug, courseSlug, lessonSlug } = pathSegmentsFromEntry(entry);

    // Re-derive a *real* analysis from the lesson's actual persisted content
    // rather than reconstructing one from the index entry's sparse metadata
    // — text-derived resources (glossary/formula/example/table) need the
    // real excerpts, which only exist by re-running the analyzer on the
    // real lesson body.
    const current = await readCurrentLesson(disciplineSlug, courseSlug, lessonSlug).catch(() => null);
    if (!current) {
      report.stillBroken.push(entry.id);
      console.warn(`[asset-maintenance] lesson for ${entry.id} no longer has a published version; skipping`);
      continue;
    }

    const analysis = await analyzeLesson(current.content);
    const plan = planLessonAssets(analysis);
    const planItem = plan.find((p) => p.resourceType === entry.resource_type);
    if (!planItem) {
      // The lesson's own plan no longer wants this resource type (content changed) — nothing to replace it with.
      report.stillBroken.push(entry.id);
      continue;
    }

    const validate = createAssetValidator({ isDuplicateChecksum: duplicateCheckExcluding(entry.id) });
    const { accepted } = await chain.resolveMany({ ...planItem, quantity: 1 }, analysis, { validate });
    if (!accepted.length) {
      report.stillBroken.push(entry.id);
      console.warn(`[asset-maintenance] no replacement found for ${entry.id}; needs manual attention`);
      continue;
    }

    const version = await getCurrentVersion(disciplineSlug, courseSlug, lessonSlug);
    if (!version) {
      report.stillBroken.push(entry.id);
      continue;
    }

    const { allAssets } = await replaceAssetInVersion(
      disciplineSlug,
      courseSlug,
      lessonSlug,
      version,
      entry.id,
      accepted[0]
    );
    await upsertLessonEntries(entry.lesson_id, allAssets);
    report.replaced.push(entry.id);
    console.warn(`[asset-maintenance] replaced ${entry.id} via ${accepted[0].candidate.provider}`);
  }

  return report;
}
