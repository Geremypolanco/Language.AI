/**
 * Every resource provider (local library, Wikimedia, OER, AI generation,
 * diagram generator, audio synthesis...) implements this same shape so the
 * ResourcePriorityChain can call any of them interchangeably. Adding a new
 * source of assets never requires touching the pipeline, planner, or
 * validator — only a new subclass of this.
 */
export class AssetProvider {
  constructor(name) {
    if (new.target === AssetProvider) {
      throw new Error('AssetProvider is abstract — subclass it.');
    }
    this.name = name;
  }

  /**
   * Finds candidate assets for one plan item.
   * @param {object} planItem - an AssetPlanItem (resourceType, searchTerms, preferredFormat, ...)
   * @param {object} analysis - the lesson's AssetAnalyzer output
   * @returns {Promise<Candidate[]>} candidates, or [] if this provider has nothing —
   *   never throws for "no results", only for genuine failures (network error, etc.),
   *   which the priority chain treats the same as an empty result and moves on.
   *
   * Candidate shape:
   * {
   *   provider: string, resourceType: string, format: string, title: string,
   *   license: string, keywords: string[],
   *   bytes?: Buffer,        // generated/downloaded content ready to persist
   *   sourceUrl?: string,    // where it came from, for attribution/audit
   *   width?: number, height?: number, duration_seconds?: number,
   *   raw?: object,          // provider-specific debug metadata
   * }
   */
  // eslint-disable-next-line no-unused-vars
  async find(planItem, analysis) {
    throw new Error(`${this.name} must implement find()`);
  }
}
