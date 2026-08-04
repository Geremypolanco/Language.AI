import { AssetProvider } from './AssetProvider.js';
import { env } from '../../config/env.js';

/**
 * Build-time text-to-speech generation for pronunciations, readings,
 * explanations, and dialogue lines. Targets a generic TTS REST shape
 * (POST {text, language} -> audio bytes) — point ASSET_TTS_BASE_URL/API_KEY
 * at ElevenLabs, Azure Speech, Amazon Polly, etc.
 *
 * One candidate is generated per search term (each vocabulary word gets its
 * own pronunciation clip) up to the plan item's requested quantity.
 * Unconfigured, returns no candidates.
 */
export class AudioProvider extends AssetProvider {
  constructor({ timeoutMs = 15_000 } = {}) {
    super('ai-tts');
    this.timeoutMs = timeoutMs;
  }

  async find(planItem, analysis) {
    if (!env.ttsApiKey || !env.ttsBaseUrl) return [];
    if (planItem.resourceType !== 'audio') return [];

    const terms = (planItem.searchTerms.length ? planItem.searchTerms : [analysis.mainTopic]).slice(
      0,
      planItem.quantity
    );

    const candidates = [];
    for (const term of terms) {
      const audio = await this.#synthesize(term, analysis.language).catch((err) => {
        console.warn(`[${this.name}] synthesis failed for "${term}": ${err.message}`);
        return null;
      });
      if (!audio) continue;
      candidates.push({
        provider: this.name,
        resourceType: 'audio',
        format: audio.format,
        title: term,
        license: 'proprietary-generated',
        keywords: [term],
        bytes: audio.bytes,
        duration_seconds: audio.durationSeconds,
        raw: { text: term },
      });
    }
    return candidates;
  }

  async #synthesize(text, language) {
    const res = await fetch(`${env.ttsBaseUrl}/v1/speech`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.ttsApiKey}` },
      body: JSON.stringify({ text, language }),
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    if (!res.ok) throw new Error(`TTS request failed: ${res.status}`);
    const bytes = Buffer.from(await res.arrayBuffer());
    return { bytes, format: 'mp3', durationSeconds: undefined };
  }
}
