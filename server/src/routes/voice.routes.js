import { Router } from 'express';
import { createVoiceSessionSchema, voiceTurnSchema } from '../schemas/voiceSchemas.js';
import {
  createSession,
  getSession,
  endSession,
  appendTurn,
  setSessionLanguage,
  toClientView,
} from '../services/voice/conversationSession.js';
import { buildSystemPrompt } from '../services/voice/promptTemplates.js';
import { streamAiReply } from '../services/voice/streamingAiClient.js';
import { scanForInjection } from '../services/promptGuard.js';
import { isOverconfident } from '../services/outputGuard.js';
import { createVoiceRateLimiter } from '../middleware/rateLimiter.js';

export const voiceRouter = Router();
const voiceRateLimiter = await createVoiceRateLimiter();

voiceRouter.post('/session', (req, res) => {
  const parsed = createVoiceSessionSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ error: 'invalid_request', details: parsed.error.flatten() });
  }
  const session = createSession(parsed.data);
  res.status(201).json(toClientView(session));
});

// Used on reconnect to restore (or discover the loss of) a session's state.
voiceRouter.get('/session/:id', (req, res) => {
  const session = getSession(req.params.id);
  if (!session) {
    return res.status(404).json({ error: 'session_not_found', message: 'Session expired or does not exist. Start a new one.' });
  }
  res.json(toClientView(session));
});

voiceRouter.delete('/session/:id', (req, res) => {
  endSession(req.params.id);
  res.json({ ok: true });
});

/**
 * Streams one conversational turn as Server-Sent Events. The client keeps
 * the request open only as long as it wants the reply spoken: on barge-in it
 * aborts the fetch, which propagates to `signal` here and stops the upstream
 * LLM call immediately — no wasted generation, no orphaned audio.
 */
voiceRouter.post('/converse', voiceRateLimiter, async (req, res) => {
  const parsed = voiceTurnSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ error: 'invalid_request', details: parsed.error.flatten() });
  }
  const { sessionId, message, language } = parsed.data;

  const session = getSession(sessionId);
  if (!session) {
    return res.status(404).json({ error: 'session_not_found', message: 'Session expired or does not exist. Start a new one.' });
  }

  const injectionCheck = scanForInjection(message);
  if (injectionCheck.suspicious) {
    return res.status(422).json({
      error: 'input_rejected',
      message: 'Your message was flagged by our content safety filters. Please rephrase it.',
    });
  }

  if (language && language !== session.language) {
    setSessionLanguage(session, language);
  }

  let systemPrompt = buildSystemPrompt(session);
  if (session.summary) {
    systemPrompt += `\n\nSummary of the conversation so far: ${session.summary}`;
  }
  const messages = [...session.history.map(({ role, content }) => ({ role, content })), { role: 'user', content: message }];

  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive',
    'X-Accel-Buffering': 'no',
  });

  const abortController = new AbortController();
  // req.destroyed is unreliable here: express.json() already fully consumed
  // the request stream to parse the body, so the readable side can look
  // "destroyed" long before the client's connection actually closes. Track
  // disconnection explicitly via the 'close' event instead.
  let clientDisconnected = false;
  req.on('close', () => {
    clientDisconnected = true;
    abortController.abort();
  });

  let fullReply = '';
  let interrupted = false;
  try {
    for await (const chunk of streamAiReply({ systemPrompt, messages, signal: abortController.signal })) {
      fullReply += chunk;
      res.write(`data: ${JSON.stringify({ type: 'delta', text: chunk })}\n\n`);
    }
  } catch (err) {
    if (err?.name === 'AbortError') {
      interrupted = true;
    } else {
      console.error('[voice.routes] stream failed', err);
      if (!res.writableEnded) {
        res.write(`data: ${JSON.stringify({ type: 'error', message: 'The AI service is temporarily unavailable.' })}\n\n`);
      }
    }
  }

  if (clientDisconnected) return; // client already gone, nothing left to write

  await appendTurn(session, 'user', message);
  if (fullReply.trim()) {
    await appendTurn(session, 'assistant', interrupted ? `${fullReply.trim()} [interrupted by user]` : fullReply.trim());
  }

  res.write(
    `data: ${JSON.stringify({
      type: 'done',
      interrupted,
      flagged: isOverconfident(fullReply),
      language: session.language,
    })}\n\n`
  );
  res.end();
});
