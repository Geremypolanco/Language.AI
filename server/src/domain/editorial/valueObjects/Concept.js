import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';

/** A discrete unit of knowledge a lesson can teach or an exercise can target. */
export class Concept extends DomainEntity {
  static schema = z.object({
    id: z.string().min(1),
    name: z.string().min(1),
    description: z.string().optional(),
    discipline: z.string().optional(),
  });

  matchesKeyword(keyword) {
    const needle = keyword.toLowerCase();
    return this.name.toLowerCase().includes(needle) || Boolean(this.description?.toLowerCase().includes(needle));
  }
}
