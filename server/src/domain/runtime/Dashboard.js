import { z } from 'zod';
import { DomainEntity } from '../shared/DomainEntity.js';
import { CourseContent } from './CourseContent.js';
import { Assignment } from './Assignment.js';
import { Progress } from './Progress.js';

const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * A learner's aggregated summary view — built from their CourseContent,
 * Assignment, and Progress records. This is a read-side aggregate (it
 * doesn't own the underlying records, it summarizes ones passed in), but
 * it still carries real behavior rather than being a plain container: the
 * summary/upcoming/overdue/at-risk logic all lives here, once, instead of
 * being recomputed inline wherever a dashboard needs rendering.
 */
export class Dashboard extends DomainEntity {
  static schema = z.object({
    learnerId: z.string().min(1),
    generatedAt: z
      .string()
      .datetime()
      .default(() => new Date().toISOString()),
    courseContents: z.array(z.instanceof(CourseContent)).default([]),
    assignments: z.array(z.instanceof(Assignment)).default([]),
    progressRecords: z.array(z.instanceof(Progress)).default([]),
  });

  summary() {
    return {
      totalCourses: this.courseContents.length,
      averageCompletion: this.averageCompletion(),
      upcomingAssignmentsCount: this.upcomingAssignments().length,
      overdueAssignmentsCount: this.overdueAssignments().length,
    };
  }

  averageCompletion() {
    if (this.courseContents.length === 0) return 0;
    return this.courseContents.reduce((sum, c) => sum + c.completionPercentage(), 0) / this.courseContents.length;
  }

  upcomingAssignments(withinDays = 7, now = new Date()) {
    const horizon = new Date(now.getTime() + withinDays * DAY_MS);
    return this.assignments
      .filter((a) => !a.isSubmitted() && a.dueDate && new Date(a.dueDate) >= now && new Date(a.dueDate) <= horizon)
      .sort((a, b) => new Date(a.dueDate) - new Date(b.dueDate));
  }

  overdueAssignments(now = new Date()) {
    return this.assignments.filter((a) => a.isOverdue(now));
  }

  /** Courses with completion below `threshold` — a simple, transparent risk signal, not a predictive model. */
  atRiskCourses(threshold = 0.3) {
    return this.courseContents.filter((c) => c.completionPercentage() < threshold);
  }
}
