import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';

/** One log line within a PipelineExecution. */
export class BuildLog extends DomainEntity {
  static schema = z.object({
    timestamp: z.string().datetime().default(() => new Date().toISOString()),
    level: z.enum(['debug', 'info', 'warn', 'error']).default('info'),
    message: z.string().min(1),
    stage: z.string().optional(),
  });

  isError() {
    return this.level === 'error';
  }
}
