import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';

const OPTION = z.object({ id: z.string().min(1), text: z.string().min(1), correct: z.boolean().default(false) });

/**
 * The authored exercise definition (editorial side). Distinct from the
 * runtime `Exercise` model, which is a specific learner's attempt at one of
 * these — this is the template, that is the instance.
 */
export class ExercisePackage extends DomainEntity {
  static schema = z.object({
    id: z.string().min(1),
    lessonId: z.string().min(1),
    prompt: z.string().min(1),
    type: z.enum(['multiple-choice', 'open-ended', 'fill-blank', 'matching', 'coding']),
    options: z.array(OPTION).default([]),
    correctAnswer: z.string().optional(),
    difficulty: z.enum(['easy', 'medium', 'hard']).default('medium'),
    relatedConceptIds: z.array(z.string()).default([]),
  });

  isAutoGradable() {
    return this.type === 'multiple-choice' || this.type === 'matching' || this.correctAnswer != null;
  }

  /**
   * Grades a learner's response where possible. Returns `null` (not
   * false) for ungradable open-ended items without a canonical answer —
   * those need human or AI-assisted grading, which is not this model's
   * job to fake.
   */
  checkAnswer(response) {
    if (this.type === 'multiple-choice' || this.type === 'matching') {
      const correctIds = this.options.filter((o) => o.correct).map((o) => o.id);
      if (correctIds.length <= 1) return correctIds[0] === response;
      if (!Array.isArray(response)) return false;
      return [...correctIds].sort().join(',') === [...response].sort().join(',');
    }
    if (this.correctAnswer != null) {
      return (
        String(response ?? '')
          .trim()
          .toLowerCase() === this.correctAnswer.trim().toLowerCase()
      );
    }
    return null;
  }
}
