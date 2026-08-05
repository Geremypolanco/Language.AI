import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';

/**
 * The outcome of one specific check (format, license, relevance, ...).
 * Formalizes what AssetValidator previously returned as an ad-hoc
 * `{passed, reasons}` shape — every check is now a typed result instead of
 * a string pushed onto an array.
 */
export class ValidationResult extends DomainEntity {
  static schema = z.object({
    check: z.string().min(1),
    passed: z.boolean(),
    message: z.string().default(''),
    severity: z.enum(['error', 'warning', 'info']).default('error'),
  });

  /** A failed error-severity check should block acceptance; warnings/info never do. */
  isBlocking() {
    return !this.passed && this.severity === 'error';
  }
}
