import { AssetProvider } from './AssetProvider.js';
import { env } from '../../config/env.js';

const API_BASE = 'https://commons.wikimedia.org/w/api.php';

function normalizeWikimediaLicense(shortName) {
  const s = (shortName || '').toLowerCase();
  if (s.includes('cc0') || s.includes('public domain')) return 'public-domain';
  if (s.includes('cc-by-sa') || s.includes('cc by-sa')) return 'CC-BY-SA';
  if (s.includes('cc-by') || s.includes('cc by')) return 'CC-BY';
  return null; // anything else (unclear/restrictive) is not on our allow-list
}

/**
 * Real Wikimedia Commons API integration (search + imageinfo), gated by the
 * open-license allow-list before a candidate is even returned. Wikimedia's
 * API is free and keyless but requires a descriptive User-Agent per their
 * usage policy (ASSET_WIKIMEDIA_USER_AGENT).
 *
 * Only searches during find(); actual bytes are fetched via download() once
 * the priority chain has picked this candidate as the winner, so rejected
 * candidates never cost a full-file download.
 */
export class WikimediaCommonsProvider extends AssetProvider {
  constructor({ maxResults = 3, timeoutMs = 8000 } = {}) {
    super('wikimedia-commons');
    this.maxResults = maxResults;
    this.timeoutMs = timeoutMs;
  }

  async find(planItem, analysis) {
    if (!['image', 'illustration', 'gallery'].includes(planItem.resourceType)) return [];

    const query = (planItem.searchTerms.length ? planItem.searchTerms : analysis.keywords).slice(0, 3).join(' ');
    if (!query.trim()) return [];

    let titles;
    try {
      titles = await this.#search(query);
    } catch (err) {
      console.warn(`[${this.name}] search failed, yielding no candidates: ${err.message}`);
      return [];
    }

    const candidates = [];
    for (const title of titles) {
      const info = await this.#fetchFileInfo(title).catch(() => null);
      if (!info) continue; // missing info or license not on the allow-list
      candidates.push({
        provider: this.name,
        resourceType: planItem.resourceType,
        format: info.format,
        title: info.title,
        license: info.license,
        keywords: analysis.keywords,
        sourceUrl: info.url,
        width: info.width,
        height: info.height,
        raw: { wikimediaTitle: title },
      });
    }
    return candidates;
  }

  async #request(params) {
    const url = new URL(API_BASE);
    for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
    const res = await fetch(url, {
      headers: { 'User-Agent': env.wikimediaUserAgent },
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    if (!res.ok) throw new Error(`Wikimedia API request failed: ${res.status}`);
    return res.json();
  }

  async #search(query) {
    const body = await this.#request({
      action: 'query',
      list: 'search',
      srsearch: query,
      srnamespace: '6', // File: namespace
      srlimit: String(this.maxResults),
      format: 'json',
    });
    return (body.query?.search || []).map((r) => r.title);
  }

  async #fetchFileInfo(title) {
    const body = await this.#request({
      action: 'query',
      titles: title,
      prop: 'imageinfo',
      iiprop: 'url|size|extmetadata',
      format: 'json',
    });
    const pages = body.query?.pages || {};
    const page = Object.values(pages)[0];
    const info = page?.imageinfo?.[0];
    if (!info) return null;

    const license = normalizeWikimediaLicense(info.extmetadata?.LicenseShortName?.value);
    if (!license) return null;

    return {
      title: (page.title || title).replace(/^File:/, ''),
      url: info.url,
      width: info.width,
      height: info.height,
      format: (info.url.split('.').pop() || 'jpg').toLowerCase(),
      license,
    };
  }

  /** Fetches the actual bytes for a candidate already chosen by the priority chain. */
  async download(sourceUrl) {
    const res = await fetch(sourceUrl, {
      headers: { 'User-Agent': env.wikimediaUserAgent },
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    if (!res.ok) throw new Error(`Wikimedia file download failed: ${res.status}`);
    return Buffer.from(await res.arrayBuffer());
  }
}
