import { AssetProvider } from './AssetProvider.js';
import { env } from '../../config/env.js';

const API_BASE = 'https://www.googleapis.com/customsearch/v1';

/**
 * Google Programmable Search (Custom Search JSON API) restricted to image
 * results — this is the *second-to-last* resort per the priority chain,
 * ahead only of AI generation, precisely because general web image search
 * carries the weakest license guarantees of any source here. Results are
 * filtered to Google's own `rights` license facet; anything without a clear
 * reusable license is dropped rather than assumed safe.
 *
 * Requires a paid/quota-limited Google Cloud API key and a Programmable
 * Search Engine ID. Unconfigured, returns no candidates.
 */
export class GoogleImagesProvider extends AssetProvider {
  constructor({ timeoutMs = 8000 } = {}) {
    super('google-images');
    this.timeoutMs = timeoutMs;
  }

  async find(planItem, analysis) {
    if (!env.googleCseApiKey || !env.googleCseId) return [];
    if (!['image', 'illustration', 'gallery'].includes(planItem.resourceType)) return [];

    const query = (planItem.searchTerms.length ? planItem.searchTerms : analysis.keywords).slice(0, 4).join(' ');
    if (!query.trim()) return [];

    const url = new URL(API_BASE);
    url.searchParams.set('key', env.googleCseApiKey);
    url.searchParams.set('cx', env.googleCseId);
    url.searchParams.set('q', query);
    url.searchParams.set('searchType', 'image');
    // Restrict to results Google labels as freely reusable — never trust an unlicensed result.
    url.searchParams.set('rights', 'cc_publicdomain|cc_attribute|cc_sharealike');
    url.searchParams.set('num', '5');

    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(this.timeoutMs) });
      if (!res.ok) throw new Error(`Google CSE request failed: ${res.status}`);
      const body = await res.json();

      return (body.items || []).map((item) => ({
        provider: this.name,
        resourceType: planItem.resourceType,
        format: (item.link.split('.').pop() || 'jpg').toLowerCase().split('?')[0],
        title: item.title,
        license: 'CC-BY', // best-effort from the rights-filtered query; validated again downstream
        keywords: analysis.keywords,
        sourceUrl: item.link,
        width: item.image?.width,
        height: item.image?.height,
        raw: { contextLink: item.image?.contextLink },
      }));
    } catch (err) {
      console.warn(`[${this.name}] search failed, yielding no candidates: ${err.message}`);
      return [];
    }
  }

  async download(sourceUrl) {
    const res = await fetch(sourceUrl, { signal: AbortSignal.timeout(this.timeoutMs) });
    if (!res.ok) throw new Error(`Google image download failed: ${res.status}`);
    return Buffer.from(await res.arrayBuffer());
  }
}
