import { z } from 'zod';
import { DomainEntity } from '../shared/DomainEntity.js';
import { CourseContent } from './CourseContent.js';

/** A learner's enrolled view of a curriculum — references the editorial `CurriculumPackage` only by id. */
export class Curriculum extends DomainEntity {
  static schema = z.object({
    id: z.string().min(1),
    learnerId: z.string().min(1),
    curriculumPackageId: z.string().min(1),
    courseContents: z.array(z.instanceof(CourseContent)).default([]),
    enrolledAt: z.string().datetime().default(() => new Date().toISOString()),
  });

  overallProgress() {
    if (this.courseContents.length === 0) return 0;
    const total = this.courseContents.reduce((sum, c) => sum + c.completionPercentage(), 0);
    return total / this.courseContents.length;
  }

  findCourseContent(coursePackageId) {
    return this.courseContents.find((c) => c.coursePackageId === coursePackageId) ?? null;
  }

  isComplete() {
    return this.courseContents.length > 0 && this.courseContents.every((c) => c.isComplete());
  }
}
