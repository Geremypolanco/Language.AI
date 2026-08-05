import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';
import { ExercisePackage } from './ExercisePackage.js';

const RUBRIC_CRITERION = z.object({
  criterionId: z.string().min(1),
  description: z.string().min(1),
  maxPoints: z.number().positive(),
});

/**
 * A graded assessment grouping exercises under a rubric. Per the domain
 * spec this must know its rubrics, criteria, and how to evaluate a
 * submission — `evaluate()` is real grading logic, not a data bag a route
 * handler has to reimplement.
 */
export class AssessmentPackage extends DomainEntity {
  static schema = z.object({
    id: z.string().min(1),
    lessonId: z.string().min(1),
    title: z.string().min(1),
    exercises: z.array(z.instanceof(ExercisePackage)).default([]),
    rubrics: z.array(RUBRIC_CRITERION).default([]),
    passingScore: z.number().min(0).max(1).default(0.6),
  });

  totalPossiblePoints() {
    return this.rubrics.reduce((sum, r) => sum + r.maxPoints, 0);
  }

  /**
   * @param responses {Record<string, unknown>} exerciseId -> learner response
   * @returns {{ results: Array<{exerciseId: string, correct: boolean|null}>, score: number, passed: boolean }}
   */
  evaluate(responses) {
    const results = this.exercises.map((exercise) => ({
      exerciseId: exercise.id,
      correct: exercise.checkAnswer(responses[exercise.id]),
    }));

    const gradable = results.filter((r) => r.correct !== null);
    const correctCount = gradable.filter((r) => r.correct).length;
    const score = gradable.length ? correctCount / gradable.length : 0;

    return { results, score, passed: score >= this.passingScore, ungradableCount: results.length - gradable.length };
  }

  isPassing(score) {
    return score >= this.passingScore;
  }
}
