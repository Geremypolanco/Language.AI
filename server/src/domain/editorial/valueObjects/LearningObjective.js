import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';

/** Bloom's taxonomy levels, ordered from lowest to highest cognitive demand. */
export const BLOOM_LEVELS = Object.freeze(['remember', 'understand', 'apply', 'analyze', 'evaluate', 'create']);

const HIGHER_ORDER_LEVELS = new Set(['analyze', 'evaluate', 'create']);

/** What a learner should be able to do after a lesson/course — the unit CurriculumPackage coverage is measured against. */
export class LearningObjective extends DomainEntity {
  static schema = z.object({
    id: z.string().min(1),
    statement: z.string().min(1),
    bloomLevel: z.enum(BLOOM_LEVELS).default('understand'),
    relatedCompetencyIds: z.array(z.string()).default([]),
  });

  /** Higher-order objectives (analyze/evaluate/create) generally need active practice, not just reading — used by planners deciding exercise depth. */
  isHigherOrder() {
    return HIGHER_ORDER_LEVELS.has(this.bloomLevel);
  }

  cognitiveRank() {
    return BLOOM_LEVELS.indexOf(this.bloomLevel);
  }
}
