import { z } from 'zod';
import { DomainEntity } from '../shared/DomainEntity.js';

/**
 * Tracks one learner's completion/mastery of one target (lesson, course, or
 * competency). References the editorial package it tracks only by id
 * (`targetId`) — runtime never imports editorial classes, keeping the two
 * domains structurally separate.
 */
export class Progress extends DomainEntity {
  static schema = z.object({
    id: z.string().min(1),
    learnerId: z.string().min(1),
    targetType: z.enum(['lesson', 'course', 'competency']),
    targetId: z.string().min(1),
    status: z.enum(['not-started', 'in-progress', 'completed']).default('not-started'),
    completionRatio: z.number().min(0).max(1).default(0),
    masteryScore: z.number().min(0).max(1).optional(),
    startedAt: z.string().datetime().optional(),
    completedAt: z.string().datetime().optional(),
    updatedAt: z.string().datetime().default(() => new Date().toISOString()),
  });

  recordCompletion(ratio) {
    this.completionRatio = Math.max(0, Math.min(1, ratio));
    this.updatedAt = new Date().toISOString();
    if (this.status === 'not-started' && this.completionRatio > 0) {
      this.status = 'in-progress';
      this.startedAt ??= this.updatedAt;
    }
    if (this.completionRatio >= 1) {
      this.status = 'completed';
      this.completedAt = this.updatedAt;
    }
    return this;
  }

  recordMastery(score) {
    this.masteryScore = Math.max(0, Math.min(1, score));
    this.updatedAt = new Date().toISOString();
    return this;
  }

  /** Categorical bucket for display — thresholds are deliberately coarse (this is a progress summary, not a grading rubric). */
  masteryLevel() {
    if (this.masteryScore == null) return 'unassessed';
    if (this.masteryScore >= 0.85) return 'advanced';
    if (this.masteryScore >= 0.6) return 'proficient';
    if (this.masteryScore > 0) return 'developing';
    return 'novice';
  }

  isComplete() {
    return this.status === 'completed';
  }
}
