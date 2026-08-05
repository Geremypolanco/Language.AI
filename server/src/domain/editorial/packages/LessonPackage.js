import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';
import { lessonContentSchema } from '../../../asset-builder/schemas.js';
import { LearningObjective, BLOOM_LEVELS } from '../valueObjects/LearningObjective.js';
import { ExercisePackage } from './ExercisePackage.js';
import { AssessmentPackage } from './AssessmentPackage.js';
import { AcademicAssetPackage } from './AcademicAssetPackage.js';

/**
 * A lesson as the editorial pipeline builds it. Extends the existing
 * `lessonContentSchema` (asset-builder's input contract) rather than
 * redefining lessonId/courseId/discipline/language/level/title/sections —
 * that schema is the stable contract the Academic Asset Builder already
 * consumes, and `toLessonContent()` below is the adapter that keeps feeding
 * it unchanged.
 */
export class LessonPackage extends DomainEntity {
  static schema = lessonContentSchema.extend({
    learningObjectives: z.array(z.instanceof(LearningObjective)).default([]),
    exercises: z.array(z.instanceof(ExercisePackage)).default([]),
    assessments: z.array(z.instanceof(AssessmentPackage)).default([]),
    academicAssets: z.instanceof(AcademicAssetPackage).optional(),
  });

  /** Adapter back to the plain shape the existing asset-builder pipeline (buildLessonAssets) expects — no changes needed on that side. */
  toLessonContent() {
    const { lessonId, courseId, discipline, language, level, title, objectives, sections } = this;
    return { lessonId, courseId, discipline, language, level, title, objectives, sections };
  }

  isReadyForPublication() {
    if (this.learningObjectives.length === 0) return false;
    if (this.academicAssets?.hasRequiredGaps()) return false;
    return true;
  }

  objectiveCoverageByBloomLevel() {
    const counts = Object.fromEntries(BLOOM_LEVELS.map((level) => [level, 0]));
    for (const objective of this.learningObjectives) counts[objective.bloomLevel] += 1;
    return counts;
  }
}
