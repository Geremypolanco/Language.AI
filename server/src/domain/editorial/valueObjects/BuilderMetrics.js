import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';

/** Quantitative outcome of one builder run — what BuilderResult reports alongside its output. */
export class BuilderMetrics extends DomainEntity {
  static schema = z.object({
    assetsBuilt: z.number().int().min(0).default(0),
    assetsReused: z.number().int().min(0).default(0),
    assetsUnresolved: z.number().int().min(0).default(0),
    providersInvoked: z.number().int().min(0).default(0),
    durationMs: z.number().min(0).optional(),
  });

  totalAssets() {
    return this.assetsBuilt + this.assetsReused;
  }

  /** Fraction of resolved assets that came from reuse rather than fresh generation/fetch — the metric the whole "own a library" architecture exists to maximize. */
  reuseRatio() {
    const total = this.totalAssets();
    return total === 0 ? 0 : this.assetsReused / total;
  }
}
