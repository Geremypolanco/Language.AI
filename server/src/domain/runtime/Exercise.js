import { z } from 'zod';
import { DomainEntity } from '../shared/DomainEntity.js';

/**
 * A learner's attempt at an exercise. This is deliberately *not* the
 * exercise definition — that's the editorial `ExercisePackage`, referenced
 * here only by id (`exercisePackageId`). Grading logic (checkAnswer) lives
 * on ExercisePackage; this model only records the attempt and its outcome,
 * so runtime code never needs to import an editorial class to work with a
 * student's submission.
 */
export class Exercise extends DomainEntity {
  static schema = z.object({
    id: z.string().min(1),
    learnerId: z.string().min(1),
    exercisePackageId: z.string().min(1),
    response: z.unknown().optional(),
    attempts: z.number().int().min(0).default(0),
    maxAttempts: z.number().int().positive().optional(),
    correct: z.boolean().nullable().default(null),
    completedAt: z.string().datetime().optional(),
  });

  submit(response) {
    if (!this.canRetry()) throw new Error(`Exercise ${this.id} has no attempts remaining.`);
    this.response = response;
    this.attempts += 1;
    return this;
  }

  /** Records a grading outcome computed elsewhere (by the matching ExercisePackage.checkAnswer). */
  recordGrade(isCorrect) {
    this.correct = isCorrect;
    if (isCorrect) this.completedAt = new Date().toISOString();
    return this;
  }

  attemptsRemaining() {
    if (this.maxAttempts == null) return Infinity;
    return Math.max(0, this.maxAttempts - this.attempts);
  }

  canRetry() {
    return this.correct !== true && this.attemptsRemaining() > 0;
  }
}
