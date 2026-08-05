import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';
import { PublicationVersion } from './PublicationVersion.js';
import { AssetManifest } from '../packages/AssetManifest.js';

/** Everything published for one course/curriculum at its current version — content plus every lesson's asset manifest. */
export class PublicationManifest extends DomainEntity {
  static schema = z.object({
    targetType: z.enum(['course', 'curriculum']),
    targetId: z.string().min(1),
    version: z.instanceof(PublicationVersion),
    assetManifests: z.array(z.instanceof(AssetManifest)).default([]),
  });

  totalAssets() {
    return this.assetManifests.reduce((sum, m) => sum + m.totalAssets(), 0);
  }

  getManifestForLesson(lessonId) {
    return this.assetManifests.find((m) => m.lessonId === lessonId) ?? null;
  }
}
