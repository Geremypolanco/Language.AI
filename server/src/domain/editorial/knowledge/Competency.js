import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';

/** A skill/ability a curriculum is meant to build — what CurriculumPackage.coverage() measures against. */
export class Competency extends DomainEntity {
  static schema = z.object({
    id: z.string().min(1),
    name: z.string().min(1),
    description: z.string().optional(),
    requiredConceptIds: z.array(z.string()).default([]),
  });

  /** @param objectives {import('../valueObjects/LearningObjective.js').LearningObjective[]} */
  isSatisfiedByObjectives(objectives) {
    return objectives.some((o) => o.relatedCompetencyIds.includes(this.id));
  }
}
