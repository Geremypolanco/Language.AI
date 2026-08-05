import { lessonContentSchema } from '../schemas.js';
import { analyzeLesson } from '../analyzer/AssetAnalyzer.js';
import { planLessonAssets } from '../planner/AssetPlanner.js';
import { createDefaultProviderChain } from '../providers/index.js';
import { createAssetValidator } from '../validation/AssetValidator.js';
import { queryIndex, isDuplicateChecksum } from '../persistence/libraryIndex.js';
import { getNextVersionNumber, persistLessonVersion, publishVersion } from '../persistence/AssetLibrary.js';
import { BuilderResult, BuilderMetrics, BuildLog } from '../../domain/editorial/index.js';

/**
 * The Academic Asset Builder pipeline: Analyzer -> Planner -> Providers
 * (priority chain) -> Validation -> Persistence -> Publication.
 *
 * This is the *only* place in the codebase that is allowed to search for or
 * generate educational resources. It runs at content-build time, driven by
 * whoever authors/updates a lesson — never by a student's request. The
 * student-facing routes (see routes/academy.routes.js) only ever read what
 * this function already persisted.
 *
 * A required plan item that no provider can resolve does NOT fail the whole
 * build — it's recorded in `unresolved` so authors can follow up, while
 * everything else still gets built and published.
 */
export async function buildLessonAssets(rawLesson, { publish = true } = {}) {
  const lesson = lessonContentSchema.parse(rawLesson);

  const analysis = await analyzeLesson(lesson);
  const plan = planLessonAssets(analysis);

  const chain = createDefaultProviderChain({ queryIndex });
  const validate = createAssetValidator({ isDuplicateChecksum });

  const resolvedAssets = [];
  const unresolved = [];

  for (const planItem of plan) {
    const { accepted, attempts } = await chain.resolveMany(planItem, analysis, { validate });
    resolvedAssets.push(...accepted);

    const missing = planItem.quantity - accepted.length;
    if (missing > 0) {
      unresolved.push({ planItem, missing, attempts });
    }
  }

  const version = await getNextVersionNumber(lesson.discipline, lesson.courseId, lesson.lessonId);
  const { dir, assets } = await persistLessonVersion({ lesson, resolvedAssets, version });

  if (publish) {
    await publishVersion(lesson.discipline, lesson.courseId, lesson.lessonId, version);
  }

  if (unresolved.length) {
    console.warn(
      `[asset-builder] lesson "${lesson.lessonId}" v${version} has ${unresolved.length} unresolved plan item(s):`,
      unresolved.map(
        (u) =>
          `${u.planItem.resourceType} (missing ${u.missing}/${u.planItem.quantity}, priority: ${u.planItem.priority})`
      )
    );
  }

  const builderResult = buildBuilderResult({ lesson, resolvedAssets, unresolved });

  return {
    lessonId: lesson.lessonId,
    version,
    published: publish,
    directory: dir,
    plan,
    assets,
    unresolved,
    builderResult,
  };
}

/** Formalizes this run's outcome as a typed BuilderResult instead of the caller re-deriving success/metrics from raw arrays. */
function buildBuilderResult({ lesson, resolvedAssets, unresolved }) {
  const assetsBuilt = resolvedAssets.filter((r) => r.candidate.provider !== 'local-library').length;
  const assetsReused = resolvedAssets.filter((r) => r.candidate.provider === 'local-library').length;
  const assetsUnresolved = unresolved.reduce((sum, u) => sum + u.missing, 0);
  const hasRequiredGaps = unresolved.some((u) => u.planItem.priority === 'required');

  const invokedProviders = new Set([
    ...resolvedAssets.map((r) => r.candidate.provider),
    ...unresolved.flatMap((u) => u.attempts.map((a) => a.provider)),
  ]);

  return new BuilderResult({
    success: !hasRequiredGaps,
    targetId: lesson.lessonId,
    metrics: new BuilderMetrics({
      assetsBuilt,
      assetsReused,
      assetsUnresolved,
      providersInvoked: invokedProviders.size,
    }),
    logs: unresolved.map(
      (u) =>
        new BuildLog({
          level: 'warn',
          stage: 'providers',
          message: `${u.planItem.resourceType} unresolved: missing ${u.missing}/${u.planItem.quantity} (priority: ${u.planItem.priority})`,
        })
    ),
  });
}
