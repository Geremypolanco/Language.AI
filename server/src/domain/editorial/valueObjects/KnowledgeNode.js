import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';

/** One node in a KnowledgeGraph — a concept, competency, objective, or course, plus what it connects to. */
export class KnowledgeNode extends DomainEntity {
  static schema = z.object({
    id: z.string().min(1),
    type: z.enum(['concept', 'competency', 'objective', 'course']),
    label: z.string().min(1),
    relatedNodeIds: z.array(z.string()).default([]),
  });

  isRelatedTo(nodeId) {
    return this.relatedNodeIds.includes(nodeId);
  }
}
