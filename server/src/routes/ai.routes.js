import { Router } from 'express';
import { randomUUID } from 'node:crypto';
import { aiChatRequestSchema } from '../schemas/aiSchemas.js';
import { scanForInjection } from '../services/promptGuard.js';
import { callAiProvider } from '../services/aiClient.js';
import { validateAiOutput } from '../services/outputGuard.js';
import { createAiRateLimiter } from '../middleware/rateLimiter.js';

export const aiRouter = Router();
const aiRateLimiter = await createAiRateLimiter();

aiRouter.post('/chat', aiRateLimiter, async (req, res) => {
  // 1. Structural input validation (Zod) — length caps and required fields.
  const parsedRequest = aiChatRequestSchema.safeParse(req.body);
  if (!parsedRequest.success) {
    return res.status(400).json({ error: 'invalid_request', details: parsedRequest.error.flatten() });
  }
  const { message } = parsedRequest.data;

  // 2. Prompt-injection / jailbreak heuristic scan. Suspicious input is not
  // silently forwarded to the model — it is rejected with a clear reason.
  const injectionCheck = scanForInjection(message);
  if (injectionCheck.suspicious) {
    return res.status(422).json({
      error: 'input_rejected',
      message: 'Your message was flagged by our content safety filters. Please rephrase it.',
    });
  }

  try {
    // 3. Call the model (input is sanitized upstream by sanitizeBody + wrapped
    // as untrusted data inside the prompt by callAiProvider).
    const rawOutput = await callAiProvider(message);

    // 4. Structural + heuristic output validation before it ever reaches the client.
    const validated = validateAiOutput(rawOutput);
    if (!validated.ok) {
      console.error('[ai.routes] provider returned invalid output shape', validated.error);
      return res.status(502).json({
        error: 'invalid_ai_output',
        message: 'The AI response could not be validated and was blocked for your safety.',
      });
    }

    return res.json({
      messageId: randomUUID(),
      conversationId: parsedRequest.data.conversationId ?? randomUUID(),
      ...validated.data,
    });
  } catch (err) {
    console.error('[ai.routes] provider call failed', err);
    return res.status(502).json({ error: 'ai_provider_error', message: 'The AI service is temporarily unavailable.' });
  }
});
