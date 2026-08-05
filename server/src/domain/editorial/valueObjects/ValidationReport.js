import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';
import { ValidationResult } from './ValidationResult.js';

/** Aggregates every ValidationResult produced while checking one candidate/package. */
export class ValidationReport extends DomainEntity {
  static schema = z.object({
    targetId: z.string().min(1),
    targetType: z.string().default('asset'),
    generatedAt: z
      .string()
      .datetime()
      .default(() => new Date().toISOString()),
    results: z.array(z.instanceof(ValidationResult)).default([]),
  });

  isValid() {
    return this.results.every((r) => !r.isBlocking());
  }

  blockingFailures() {
    return this.results.filter((r) => r.isBlocking());
  }

  warnings() {
    return this.results.filter((r) => !r.passed && r.severity === 'warning');
  }
}
