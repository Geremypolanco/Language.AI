import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';
import { CurriculumPackage } from './CurriculumPackage.js';

/** The root of one content submission — what "Content Builder" produces, containing one or more curricula. */
export class ContentPackage extends DomainEntity {
  static schema = z.object({
    id: z.string().min(1),
    title: z.string().min(1),
    curricula: z.array(z.instanceof(CurriculumPackage)).default([]),
    createdAt: z
      .string()
      .datetime()
      .default(() => new Date().toISOString()),
    createdBy: z.string().optional(),
  });

  totalCourses() {
    return this.curricula.reduce((sum, c) => sum + c.courses.length, 0);
  }

  totalLessons() {
    return this.curricula.reduce((sum, c) => sum + c.courses.reduce((s, course) => s + course.totalLessons(), 0), 0);
  }

  isReadyForPublication() {
    return this.curricula.length > 0 && this.curricula.every((c) => c.isReadyForPublication());
  }
}
