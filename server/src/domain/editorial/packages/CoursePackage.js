import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';
import { LessonPackage } from './LessonPackage.js';
import { CourseDependency } from '../valueObjects/CourseDependency.js';

export class CoursePackage extends DomainEntity {
  static schema = z.object({
    id: z.string().min(1),
    title: z.string().min(1),
    discipline: z.string().min(1),
    lessons: z.array(z.instanceof(LessonPackage)).default([]),
    dependencies: z.array(z.instanceof(CourseDependency)).default([]),
  });

  totalLessons() {
    return this.lessons.length;
  }

  findLesson(lessonId) {
    return this.lessons.find((l) => l.lessonId === lessonId) ?? null;
  }

  /** This course's own dependencies (courses it requires), not dependencies pointing at it. */
  hardDependencies() {
    return this.dependencies.filter((d) => d.courseId === this.id && d.blocksAccess());
  }

  isReadyForPublication() {
    return this.lessons.length > 0 && this.lessons.every((l) => l.isReadyForPublication());
  }
}
