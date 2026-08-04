import { AssetProvider } from './AssetProvider.js';

/**
 * First stop in the priority chain: reuse an asset the library already has
 * (from this lesson's own prior version, or from an unrelated lesson that
 * happens to cover the same concept) instead of fetching/generating a new
 * one. This is what keeps the platform's external-call volume flat as the
 * catalog grows into the millions of lessons the spec targets.
 *
 * Takes `queryIndex` as a dependency instead of importing AssetLibrary
 * directly, so this provider stays testable/swappable without a filesystem.
 */
export class LocalLibraryProvider extends AssetProvider {
  constructor({ queryIndex }) {
    super('local-library');
    this.queryIndex = queryIndex;
  }

  async find(planItem, analysis) {
    const matches = await this.queryIndex({
      resourceType: planItem.resourceType,
      keywords: planItem.searchTerms.length ? planItem.searchTerms : analysis.keywords,
      language: analysis.language,
    });

    return matches.map((m) => ({
      provider: this.name,
      resourceType: planItem.resourceType,
      format: m.format,
      title: m.title || `${planItem.resourceType} (reused)`,
      license: m.license,
      keywords: m.keywords,
      filePath: m.file_path, // already-persisted file — persistence layer will hardlink/copy, not refetch
      sourceUrl: m.source_url,
      width: m.width,
      height: m.height,
      duration_seconds: m.duration_seconds,
      raw: { reusedFromAssetId: m.id, reusedFromLessonId: m.lesson_id },
    }));
  }
}
