import fs from 'node:fs/promises';
import path from 'node:path';
import { libraryRoot } from '../persistence/paths.js';

/**
 * Walks providers in a fixed priority order — local library, persisted
 * repository, open educational resources, Wikimedia Commons, Google Images,
 * AI generation — and collects validated candidates for one plan item. This
 * is the concrete enforcement of "siempre reutilizar recursos existentes
 * antes de crear nuevos": a later provider is only ever consulted once
 * earlier ones have been exhausted for the requested quantity.
 */
export class ResourcePriorityChain {
  constructor(providers) {
    this.providers = providers;
  }

  /**
   * Collects up to `planItem.quantity` distinct, validated candidates.
   * Providers that naturally return several candidates in one find() call
   * (e.g. one audio clip per vocabulary term) are handled correctly — this
   * doesn't just take the first result and stop, and it doesn't accept two
   * candidates with identical content within the same batch.
   *
   * @param validate async (candidate, planItem, analysis) => { passed, reasons, scores, checksum }
   */
  async resolveMany(planItem, analysis, { validate }) {
    const accepted = [];
    const acceptedChecksums = new Set();
    const attempts = [];

    for (const provider of this.providers) {
      if (accepted.length >= planItem.quantity) break;

      let candidates;
      try {
        candidates = await provider.find(planItem, analysis);
      } catch (err) {
        console.warn(`[priority-chain] provider "${provider.name}" threw, skipping: ${err.message}`);
        continue;
      }

      for (const candidate of candidates) {
        if (accepted.length >= planItem.quantity) break;

        const hydrated = await this.#hydrateBytes(provider, candidate);
        if (!hydrated) continue;

        const result = await validate(hydrated, planItem, analysis);
        attempts.push({ provider: provider.name, title: candidate.title, passed: result.passed, reasons: result.reasons });
        if (!result.passed) continue;

        if (result.checksum && acceptedChecksums.has(result.checksum)) {
          attempts.push({ provider: provider.name, title: candidate.title, passed: false, reasons: ['duplicate within this batch'] });
          continue;
        }

        accepted.push({ candidate: hydrated, validation: result });
        if (result.checksum) acceptedChecksums.add(result.checksum);
      }
    }

    return { accepted, attempts };
  }

  /** Only downloads full bytes for a real contender — never for every search hit. */
  async #hydrateBytes(provider, candidate) {
    if (candidate.bytes) return candidate;

    if (candidate.filePath) {
      // Local-library reuse: the index can lag reality (e.g. a file the
      // maintenance job is mid-repair on, or removed out-of-band) — verify
      // the source actually exists before trusting it as a valid reuse
      // candidate, instead of copying a dangling reference downstream.
      try {
        await fs.access(path.join(libraryRoot(), candidate.filePath));
        return candidate;
      } catch {
        console.warn(`[priority-chain] local-library candidate references a missing file, skipping: ${candidate.filePath}`);
        return null;
      }
    }

    if (candidate.sourceUrl && typeof provider.download === 'function') {
      try {
        const bytes = await provider.download(candidate.sourceUrl);
        return { ...candidate, bytes };
      } catch (err) {
        console.warn(`[priority-chain] failed to download candidate from "${provider.name}": ${err.message}`);
        return null;
      }
    }
    return null;
  }
}
