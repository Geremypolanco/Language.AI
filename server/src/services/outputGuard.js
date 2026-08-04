import { aiChatResponseSchema } from '../schemas/aiSchemas.js';

/**
 * Phrases that tend to accompany overconfident/unverified claims — a cheap
 * proxy for hallucination risk. This does not detect factual inaccuracy (no
 * heuristic can); it flags language patterns worth a lower confidence score
 * and a UI nudge to verify, which is what the disclaimer + feedback buttons
 * are for.
 */
const OVERCONFIDENCE_PATTERNS = [
  /\b100% (certain|sure|guaranteed)\b/i,
  /\bguaranteed\b/i,
  /\bnever fails\b/i,
  /\balways true\b/i,
  /\bI (am|'m) (absolutely |completely )?certain\b/i,
];

export function isOverconfident(text) {
  return OVERCONFIDENCE_PATTERNS.some((p) => p.test(text));
}

/**
 * Validates that raw model output conforms to the strict response schema
 * before it is ever sent to the client. Anything that fails to parse is
 * rejected outright rather than passed through partially — a structural
 * guardrail against malformed or injected output shapes.
 */
export function validateAiOutput(rawOutput) {
  const parsed = aiChatResponseSchema.safeParse(rawOutput);
  if (!parsed.success) {
    return { ok: false, error: parsed.error.flatten() };
  }

  const result = { ...parsed.data };
  if (isOverconfident(result.reply) && result.confidence === 'high') {
    result.confidence = 'medium';
    result.flagged = true;
  }

  return { ok: true, data: result };
}
