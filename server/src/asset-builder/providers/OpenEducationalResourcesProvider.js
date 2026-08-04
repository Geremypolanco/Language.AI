import { AssetProvider } from './AssetProvider.js';
import { env } from '../../config/env.js';

/**
 * Open Educational Resources aggregator. There is no single canonical free
 * OER search API, so this targets a generic search endpoint shape (JSON
 * array of {title, url, license, format, width, height}) — point
 * ASSET_OER_BASE_URL at whichever OER catalog/aggregator (OER Commons,
 * Merlot, an institutional repository, ...) your deployment has access to.
 * Unconfigured, it returns no candidates rather than failing the build.
 */
export class OpenEducationalResourcesProvider extends AssetProvider {
  constructor({ timeoutMs = 8000 } = {}) {
    super('open-educational-resources');
    this.timeoutMs = timeoutMs;
  }

  async find(planItem, analysis) {
    if (!env.oerBaseUrl) return [];

    const query = (planItem.searchTerms.length ? planItem.searchTerms : analysis.keywords).slice(0, 4).join(' ');
    if (!query.trim()) return [];

    const url = new URL('/search', env.oerBaseUrl);
    url.searchParams.set('q', query);
    url.searchParams.set('type', planItem.resourceType);
    url.searchParams.set('language', analysis.language);

    try {
      const res = await fetch(url, {
        headers: env.oerApiKey ? { Authorization: `Bearer ${env.oerApiKey}` } : {},
        signal: AbortSignal.timeout(this.timeoutMs),
      });
      if (!res.ok) throw new Error(`OER search failed: ${res.status}`);
      const results = await res.json();

      return (Array.isArray(results) ? results : []).map((r) => ({
        provider: this.name,
        resourceType: planItem.resourceType,
        format: r.format,
        title: r.title,
        license: r.license,
        keywords: analysis.keywords,
        sourceUrl: r.url,
        width: r.width,
        height: r.height,
        duration_seconds: r.duration_seconds,
        raw: r,
      }));
    } catch (err) {
      console.warn(`[${this.name}] search failed, yielding no candidates: ${err.message}`);
      return [];
    }
  }

  async download(sourceUrl) {
    const res = await fetch(sourceUrl, {
      headers: env.oerApiKey ? { Authorization: `Bearer ${env.oerApiKey}` } : {},
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    if (!res.ok) throw new Error(`OER download failed: ${res.status}`);
    return Buffer.from(await res.arrayBuffer());
  }
}
