import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';
import { PublicationStatus } from '../enums.js';

/**
 * One version of a published unit. Per the domain spec this must know its
 * version, date, status, and compatibility — all four are real fields with
 * real behavior here, not just a version number sitting next to a blob.
 */
export class PublicationVersion extends DomainEntity {
  static schema = z.object({
    versionNumber: z.number().int().positive(),
    createdAt: z
      .string()
      .datetime()
      .default(() => new Date().toISOString()),
    publishedAt: z.string().datetime().optional(),
    status: z.instanceof(PublicationStatus).default(() => new PublicationStatus(PublicationStatus.DRAFT)),
    compatibleSchemaVersion: z.string().default('1.x'),
    changeSummary: z.string().optional(),
  });

  /** Major-version compatibility check (e.g. "1.x" is compatible with a runtime declaring schema "1.4"). */
  isCompatibleWith(runtimeSchemaVersion) {
    const major = (v) => v.split('.')[0];
    return major(this.compatibleSchemaVersion) === major(runtimeSchemaVersion);
  }

  publish() {
    return new PublicationVersion({
      ...this,
      status: this.status.transitionTo(PublicationStatus.PUBLISHED),
      publishedAt: new Date().toISOString(),
    });
  }

  deprecate() {
    return new PublicationVersion({ ...this, status: this.status.transitionTo(PublicationStatus.DEPRECATED) });
  }

  retract() {
    return new PublicationVersion({ ...this, status: this.status.transitionTo(PublicationStatus.RETRACTED) });
  }

  isCurrent(currentVersionNumber) {
    return this.versionNumber === currentVersionNumber && this.status.isLive();
  }
}
