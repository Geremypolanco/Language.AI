import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';
import { AssetMetadata } from '../valueObjects/AssetMetadata.js';

/**
 * The full list of assets built for one lesson version — formalizes what
 * AssetLibrary previously wrote as a hand-built `metadata.json` object.
 */
export class AssetManifest extends DomainEntity {
  static schema = z.object({
    lessonId: z.string().min(1),
    courseId: z.string().min(1),
    discipline: z.string().min(1),
    language: z.string().min(2).max(10),
    version: z.number().int().positive(),
    builtAt: z
      .string()
      .datetime()
      .default(() => new Date().toISOString()),
    assets: z.array(z.instanceof(AssetMetadata)).default([]),
  });

  totalAssets() {
    return this.assets.length;
  }

  assetCountByType() {
    const counts = {};
    for (const asset of this.assets) counts[asset.resource_type] = (counts[asset.resource_type] || 0) + 1;
    return counts;
  }

  hasResourceType(resourceType) {
    return this.assets.some((a) => a.resource_type === resourceType);
  }

  averageQuality() {
    if (this.assets.length === 0) return 0;
    return this.assets.reduce((sum, a) => sum + a.quality_score, 0) / this.assets.length;
  }
}
