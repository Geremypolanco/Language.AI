import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';
import { PublicationVersion } from './PublicationVersion.js';

const TARGET_TYPES = ['content', 'curriculum', 'course', 'lesson'];

/**
 * The live, published state for one target — what's actually being served
 * to students right now, plus its version history. This is the domain
 * model behind what `current.json` + the `versions/` directory represented
 * ad-hoc for the asset library; Publication generalizes it to any
 * publishable unit (course, curriculum, lesson), not just lesson assets.
 */
export class Publication extends DomainEntity {
  static schema = z.object({
    id: z.string().min(1),
    targetType: z.enum(TARGET_TYPES),
    targetId: z.string().min(1),
    currentVersion: z.instanceof(PublicationVersion).optional(),
    versionHistory: z.array(z.instanceof(PublicationVersion)).default([]),
  });

  publish(version) {
    // The version being superseded must move to 'deprecated', not stay
    // flagged 'published' while sitting in history — otherwise a later
    // rollbackTo() would attempt an illegal published -> published transition.
    if (this.currentVersion) this.versionHistory.push(this.currentVersion.deprecate());
    this.currentVersion = version.status.isLive() ? version : version.publish();
    return this;
  }

  rollbackTo(versionNumber) {
    const target = this.versionHistory.find((v) => v.versionNumber === versionNumber);
    if (!target) throw new Error(`Publication ${this.id} has no historical version ${versionNumber} to roll back to.`);
    if (this.currentVersion) this.versionHistory.push(this.currentVersion.deprecate());
    this.currentVersion = target.publish();
    return this;
  }

  isCompatibleWith(runtimeSchemaVersion) {
    return Boolean(this.currentVersion?.isCompatibleWith(runtimeSchemaVersion));
  }

  isLive() {
    return Boolean(this.currentVersion?.status.isLive());
  }
}
