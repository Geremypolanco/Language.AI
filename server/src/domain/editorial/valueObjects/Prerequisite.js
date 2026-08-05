import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';

/** "To access X you need Y at proficiency Z" — the edge type KnowledgeGraph and CurriculumPackage validate against. */
export class Prerequisite extends DomainEntity {
  static schema = z.object({
    requiredNodeId: z.string().min(1),
    requiredNodeType: z.enum(['concept', 'competency', 'course']),
    minimumProficiency: z.number().min(0).max(1).default(0.6),
  });

  /** @param proficiencyMap {Record<string, number>} nodeId -> proficiency 0..1 the learner currently has */
  isSatisfiedBy(proficiencyMap) {
    return (proficiencyMap[this.requiredNodeId] ?? 0) >= this.minimumProficiency;
  }
}
