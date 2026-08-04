import { env } from '../../config/env.js';
import { collectAiReply } from './streamingAiClient.js';

const SUMMARY_SYSTEM_PROMPT = [
  'You compress a spoken conversation transcript into a compact running summary.',
  "Preserve: the overall topic/goal, key facts and decisions, the user's stated preferences, and anything still unresolved.",
  'Write it as a short paragraph, third person, no more than 150 words. Do not lose continuity-critical details.',
].join(' ');

/**
 * Keeps long conversations bounded without losing continuity: once history
 * grows past a threshold, older turns are folded into a running summary and
 * only the most recent turns are kept verbatim. If summarization itself
 * fails (provider error), history is left untouched rather than silently
 * dropped — losing context is worse than a temporarily larger prompt.
 */
export async function summarizeIfNeeded(session) {
  if (session.history.length < env.voiceSummarizeAfterTurns) return;

  const keepRecent = env.voiceKeepRecentTurns;
  const cutoff = session.history.length - keepRecent;
  const toSummarize = session.history.slice(0, cutoff);
  const recent = session.history.slice(cutoff);
  if (toSummarize.length === 0) return;

  const transcript = toSummarize.map((t) => `${t.role}: ${t.content}`).join('\n');
  const priorSummary = session.summary ? `Previous summary: ${session.summary}\n\n` : '';

  let summary;
  try {
    summary = await collectAiReply({
      systemPrompt: SUMMARY_SYSTEM_PROMPT,
      messages: [{ role: 'user', content: `${priorSummary}New transcript to fold in:\n${transcript}` }],
    });
  } catch (err) {
    console.error('[memoryManager] summarization failed, keeping full history', err);
    return;
  }

  if (summary) {
    session.summary = summary;
    session.history = recent;
  }
}
