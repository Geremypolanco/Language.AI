import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';
import { AssetManifest } from './AssetManifest.js';

const UNRESOLVED_ITEM = z.object({
  resourceType: z.string(),
  missing: z.number().int().min(0),
  priority: z.enum(['required', 'recommended', 'optional']),
});

/**
 * Bridges the Academic Asset Builder pipeline's output into the editorial
 * domain for one lesson — the built AssetManifest plus whatever the
 * planner asked for that no provider could resolve.
 */
export class AcademicAssetPackage extends DomainEntity {
  static schema = z.object({
    lessonId: z.string().min(1),
    manifest: z.instanceof(AssetManifest),
    unresolvedPlanItems: z.array(UNRESOLVED_ITEM).default([]),
  });

  isComplete() {
    return this.unresolvedPlanItems.length === 0;
  }

  /** Missing an optional/recommended asset is fine to publish with; missing a required one is not. */
  hasRequiredGaps() {
    return this.unresolvedPlanItems.some((u) => u.priority === 'required');
  }

  qualitySummary() {
    return { averageQuality: this.manifest.averageQuality(), totalAssets: this.manifest.totalAssets() };
  }
}
