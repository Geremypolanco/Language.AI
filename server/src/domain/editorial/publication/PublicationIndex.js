import { z } from 'zod';
import { DomainEntity } from '../../shared/DomainEntity.js';
import { AssetMetadata } from '../valueObjects/AssetMetadata.js';

function tokenize(text) {
  return (text.toLowerCase().match(/[a-zà-öø-ÿ]+/g) || []).filter((w) => w.length > 2);
}

/**
 * The cross-lesson reuse index — every currently-published asset in the
 * library, queryable by resource type + keyword relevance. This is the
 * domain model behind what used to be a raw array read from
 * `academy/_index.json`; persistence (libraryIndex.js) now just
 * loads/saves this class's `entries` instead of hand-rolling the same
 * scoring logic inline.
 */
export class PublicationIndex extends DomainEntity {
  static schema = z.object({
    entries: z.array(z.instanceof(AssetMetadata)).default([]),
  });

  findReusable({ resourceType, keywords, language, limit = 5 }) {
    const targetTerms = new Set(tokenize(keywords.join(' ')));

    return this.entries
      .filter((e) => e.resource_type === resourceType && e.language === language)
      .map((entry) => {
        // AssetMetadata has no title field — keywords are the only real matching signal.
        const entryTerms = new Set(tokenize((entry.keywords || []).join(' ')));
        let hits = 0;
        for (const term of targetTerms) if (entryTerms.has(term)) hits += 1;
        return { entry, score: targetTerms.size ? hits / targetTerms.size : 0 };
      })
      .filter((s) => s.score > 0.2)
      .sort((a, b) => b.score - a.score)
      .slice(0, limit)
      .map((s) => s.entry);
  }

  hasChecksum(checksum) {
    if (!checksum) return false;
    return this.entries.some((e) => e.checksum_sha256 === checksum);
  }

  hasChecksumExcluding(checksum, excludeAssetId) {
    if (!checksum) return false;
    return this.entries.some((e) => e.checksum_sha256 === checksum && e.id !== excludeAssetId);
  }

  /** Replaces one lesson's entries with a fresh set — the Publication step's index update. */
  upsertLessonEntries(lessonId, newEntries) {
    this.entries = [...this.entries.filter((e) => e.lesson_id !== lessonId), ...newEntries];
    return this;
  }

  findById(assetId) {
    return this.entries.find((e) => e.id === assetId) ?? null;
  }

  size() {
    return this.entries.length;
  }
}
