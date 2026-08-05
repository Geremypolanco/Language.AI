import { z } from 'zod';
import { DomainEntity } from '../shared/DomainEntity.js';

/** A piece of work scheduled for a learner — references its editorial target (exercise/assessment/lesson) by id only. */
export class Assignment extends DomainEntity {
  static schema = z.object({
    id: z.string().min(1),
    learnerId: z.string().min(1),
    targetType: z.enum(['exercise', 'assessment', 'lesson']),
    targetId: z.string().min(1),
    assignedAt: z.string().datetime().default(() => new Date().toISOString()),
    dueDate: z.string().datetime().optional(),
    status: z.enum(['assigned', 'in-progress', 'submitted', 'graded']).default('assigned'),
    score: z.number().min(0).max(1).optional(),
  });

  /** Computed, not stored — "overdue" depends on the current time, not a status a caller has to remember to set. */
  isOverdue(now = new Date()) {
    if (!this.dueDate || this.isSubmitted()) return false;
    return new Date(this.dueDate) < now;
  }

  isSubmitted() {
    return this.status === 'submitted' || this.status === 'graded';
  }

  submit() {
    if (this.isSubmitted()) throw new Error(`Assignment ${this.id} was already submitted.`);
    this.status = 'submitted';
    return this;
  }

  grade(score) {
    if (!this.isSubmitted()) throw new Error(`Assignment ${this.id} cannot be graded before it is submitted.`);
    this.score = Math.max(0, Math.min(1, score));
    this.status = 'graded';
    return this;
  }
}
