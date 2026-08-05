import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';

/**
 * Lightweight, ephemeral checksum set scoped to a single build run — used
 * for in-batch duplicate detection (e.g. don't accept two candidates with
 * identical bytes while resolving one plan item's quantity). This is
 * distinct from PublicationIndex, which is the durable, cross-lesson reuse
 * index: CacheManifest never gets persisted to disk, it lives for the
 * duration of one ResourcePriorityChain.resolveMany() call.
 */
export class CacheManifest extends DomainEntity {
  static schema = z.object({
    scope: z.string().default('build-batch'),
    createdAt: z
      .string()
      .datetime()
      .default(() => new Date().toISOString()),
    checksums: z.array(z.string()).default([]),
  });

  has(checksum) {
    return Boolean(checksum) && this.checksums.includes(checksum);
  }

  record(checksum) {
    if (checksum && !this.has(checksum)) this.checksums.push(checksum);
    return this;
  }

  size() {
    return this.checksums.length;
  }
}
