import { collectAiReply } from '../../services/voice/streamingAiClient.js';

const ANALYSIS_SYSTEM_PROMPT = [
  'You analyze educational lesson content for an asset-building pipeline.',
  'Given the lesson text, respond with ONLY a JSON object: { "concepts": string[], "keywords": string[], "subtopics": string[] }.',
  'Concepts are the core ideas a student must learn; keywords are searchable terms for finding educational media; subtopics refine the main topic.',
  'Respond in the same language as the lesson text. Output only the JSON object, no commentary.',
].join(' ');

/**
 * Optional AI-assisted enrichment of the heuristic analysis below. Used only
 * at build time (never while a student is learning) and only when an AI
 * provider is configured — with no provider, callers get `null` and fall
 * back to the deterministic heuristics, so the pipeline stays fully
 * functional without any AI credentials.
 */
export async function aiEnhanceAnalysis(fullText) {
  try {
    const raw = await collectAiReply({
      systemPrompt: ANALYSIS_SYSTEM_PROMPT,
      messages: [{ role: 'user', content: fullText.slice(0, 6000) }],
    });
    const parsed = JSON.parse(raw);
    return {
      concepts: Array.isArray(parsed.concepts) ? parsed.concepts.filter((c) => typeof c === 'string') : [],
      keywords: Array.isArray(parsed.keywords) ? parsed.keywords.filter((k) => typeof k === 'string') : [],
      subtopics: Array.isArray(parsed.subtopics) ? parsed.subtopics.filter((s) => typeof s === 'string') : [],
    };
  } catch {
    return null;
  }
}
