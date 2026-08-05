import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';

/** "courseId depends on dependsOnCourseId" — the edge CurriculumPackage's dependency-cycle check walks. */
export class CourseDependency extends DomainEntity {
  static schema = z.object({
    courseId: z.string().min(1),
    dependsOnCourseId: z.string().min(1),
    type: z.enum(['hard', 'soft']).default('hard'),
  });

  /** A hard dependency blocks enrollment until satisfied; a soft one is only a recommendation. */
  blocksAccess() {
    return this.type === 'hard';
  }
}
