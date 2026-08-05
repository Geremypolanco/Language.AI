import { z } from 'zod';
import { DomainEntity } from '../shared/DomainEntity.js';
import { Progress } from './Progress.js';

/**
 * A learner's in-progress view of one course — references the editorial
 * `CoursePackage` only by id. `totalLessons`/`lessonOrder` are supplied by
 * the caller at construction time (the application/service layer reads
 * them from the editorial side) rather than this model reaching into
 * editorial data itself.
 */
export class CourseContent extends DomainEntity {
  static schema = z.object({
    id: z.string().min(1),
    learnerId: z.string().min(1),
    coursePackageId: z.string().min(1),
    totalLessons: z.number().int().min(0).default(0),
    lessonOrder: z.array(z.string()).default([]),
    lessonProgress: z.array(z.instanceof(Progress)).default([]),
    enrolledAt: z
      .string()
      .datetime()
      .default(() => new Date().toISOString()),
  });

  completionPercentage() {
    if (this.totalLessons === 0) return 0;
    const completed = this.lessonProgress.filter((p) => p.isComplete()).length;
    return completed / this.totalLessons;
  }

  isComplete() {
    return this.totalLessons > 0 && this.completionPercentage() >= 1;
  }

  findLessonProgress(lessonId) {
    return this.lessonProgress.find((p) => p.targetId === lessonId) ?? null;
  }

  /** First lesson in declared order without completed progress, or null if the course is finished/unordered. */
  nextIncompleteLessonId() {
    for (const lessonId of this.lessonOrder) {
      const progress = this.findLessonProgress(lessonId);
      if (!progress?.isComplete()) return lessonId;
    }
    return null;
  }
}
