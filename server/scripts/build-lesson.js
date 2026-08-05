#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import { buildLessonAssets } from '../src/asset-builder/pipeline/buildLessonAssets.js';

/**
 * Content-author entrypoint for the Academic Asset Builder. Students never
 * run this — it's invoked by whoever authors/updates lesson content
 * (manually, or from an upstream Curriculum/Lesson Builder's own pipeline)
 * to build and publish that lesson's permanent asset library entry.
 *
 * Usage: node scripts/build-lesson.js path/to/lesson.json [--no-publish]
 */
async function main() {
  const [, , lessonPathArg, ...flags] = process.argv;
  if (!lessonPathArg) {
    console.error('Usage: node scripts/build-lesson.js path/to/lesson.json [--no-publish]');
    process.exit(1);
  }

  const lessonPath = path.resolve(process.cwd(), lessonPathArg);
  const rawLesson = JSON.parse(await fs.readFile(lessonPath, 'utf8'));
  const publish = !flags.includes('--no-publish');

  console.log(`Building assets for lesson "${rawLesson.lessonId}" (publish: ${publish})...`);
  const result = await buildLessonAssets(rawLesson, { publish });

  console.log(`\nBuilt version v${result.version} at ${result.directory}`);
  console.log(`Persisted ${result.assets.length} asset(s):`);
  for (const asset of result.assets) {
    console.log(
      `  - [${asset.resource_type}] ${asset.file_path} (provider: ${asset.provider}, quality: ${asset.quality_score.toFixed(2)})`
    );
  }

  if (result.unresolved.length) {
    console.warn(`\n${result.unresolved.length} plan item(s) could not be fully resolved:`);
    for (const u of result.unresolved) {
      console.warn(
        `  - ${u.planItem.resourceType} (${u.priority ?? u.planItem.priority}): missing ${u.missing}/${u.planItem.quantity}`
      );
    }
  }

  console.log(
    result.published ? '\nPublished — students will now be served this version.' : '\nNot published (--no-publish).'
  );

  const { metrics } = result.builderResult;
  console.log(
    `\nBuilderResult: success=${result.builderResult.success} built=${metrics.assetsBuilt} reused=${metrics.assetsReused} ` +
      `unresolved=${metrics.assetsUnresolved} reuseRatio=${metrics.reuseRatio().toFixed(2)}`
  );
}

main().catch((err) => {
  console.error('Build failed:', err);
  process.exit(1);
});
