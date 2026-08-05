import { AssetProvider } from './AssetProvider.js';
import { env } from '../../config/env.js';

/**
 * Last resort in the priority chain: generates an image via an
 * OpenAI-images-compatible API when nothing reusable or open-licensed could
 * be found. Only reached when local reuse, the repository, OER, Wikimedia,
 * and (optionally) Google Images all came up empty for a *required* plan
 * item — the pipeline logs when this fires so authors can see how often
 * generation, the most expensive path, is actually needed.
 *
 * Unconfigured, returns no candidates — the build then flags the plan item
 * as unresolved for manual follow-up instead of silently failing.
 */
export class AIGenerationProvider extends AssetProvider {
  constructor({ timeoutMs = 30_000 } = {}) {
    super('ai-generation');
    this.timeoutMs = timeoutMs;
  }

  async find(planItem, analysis) {
    if (!env.imageGenApiKey || !env.imageGenBaseUrl) return [];
    if (!['image', 'illustration'].includes(planItem.resourceType)) return [];

    const subject = (planItem.searchTerms.length ? planItem.searchTerms : analysis.keywords).slice(0, 3).join(', ');
    const style =
      planItem.preferredFormat === 'scientific-illustration'
        ? 'labeled scientific illustration'
        : 'clear educational illustration';
    const prompt = `${style} of: ${subject}. Context: ${analysis.mainTopic}. Plain background, no text overlays.`;

    try {
      const res = await fetch(`${env.imageGenBaseUrl}/v1/images/generations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.imageGenApiKey}` },
        body: JSON.stringify({ prompt, n: 1, size: '1024x1024', response_format: 'b64_json' }),
        signal: AbortSignal.timeout(this.timeoutMs),
      });
      if (!res.ok) throw new Error(`Image generation request failed: ${res.status}`);
      const body = await res.json();
      const item = body.data?.[0];
      if (!item) return [];

      const bytes = item.b64_json ? Buffer.from(item.b64_json, 'base64') : null;
      if (!bytes && !item.url) return [];

      return [
        {
          provider: this.name,
          resourceType: planItem.resourceType,
          format: 'png',
          title: `${analysis.mainTopic} (AI-generated)`,
          license: 'proprietary-generated',
          keywords: analysis.keywords,
          bytes: bytes || undefined,
          sourceUrl: bytes ? undefined : item.url,
          width: 1024,
          height: 1024,
          raw: { prompt },
        },
      ];
    } catch (err) {
      console.warn(`[${this.name}] generation failed, yielding no candidates: ${err.message}`);
      return [];
    }
  }

  async download(sourceUrl) {
    const res = await fetch(sourceUrl, { signal: AbortSignal.timeout(this.timeoutMs) });
    if (!res.ok) throw new Error(`Generated image download failed: ${res.status}`);
    return Buffer.from(await res.arrayBuffer());
  }
}
