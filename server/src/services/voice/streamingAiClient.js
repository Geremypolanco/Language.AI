import { env } from '../../config/env.js';

/**
 * Resolves after `ms`, but rejects immediately (AbortError) if `signal` fires
 * first. Used to make the dev-mock stream cancel as fast as a real network
 * request would when the user barges in.
 */
function delay(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException('Aborted', 'AbortError'));
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(timer);
        reject(new DOMException('Aborted', 'AbortError'));
      },
      { once: true }
    );
  });
}

/**
 * Local fallback so the full voice pipeline (streaming, barge-in, latency
 * behavior) is testable without real AI provider credentials. Streams
 * word-by-word like a real token stream would.
 */
async function* mockStream(lastUserMessage, signal) {
  const reply = `Entiendo lo que dices sobre "${lastUserMessage.slice(0, 80)}". Cuéntame más para poder ayudarte mejor.`;
  for (const word of reply.split(' ')) {
    await delay(55, signal);
    yield `${word} `;
  }
}

/**
 * Parses an OpenAI-compatible SSE chat-completions stream, yielding each
 * text delta as it arrives.
 */
async function* parseSseStream(response, signal) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    while (true) {
      if (signal?.aborted) return;
      const { value, done } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data:')) continue;
        const data = trimmed.slice(5).trim();
        if (data === '[DONE]') return;
        try {
          const delta = JSON.parse(data).choices?.[0]?.delta?.content;
          if (delta) yield delta;
        } catch {
          // Ignore malformed/keep-alive lines rather than aborting the stream.
        }
      }
    }
  } finally {
    reader.releaseLock?.();
  }
}

/**
 * Streams an assistant reply token-by-token. `signal` (AbortSignal) cancels
 * the underlying HTTP request/local mock the instant the caller aborts it —
 * this is what makes barge-in cheap: interrupting stops generation
 * server-side too, not just audio playback client-side.
 *
 * Swap the fetch call below for your provider's real streaming SDK; nothing
 * upstream (routes, session/memory management) needs to change.
 */
export async function* streamAiReply({ systemPrompt, messages, signal }) {
  const lastUserMessage = [...messages].reverse().find((m) => m.role === 'user')?.content || '';

  if (!env.aiProviderApiKey || !env.aiProviderBaseUrl) {
    yield* mockStream(lastUserMessage, signal);
    return;
  }

  const response = await fetch(`${env.aiProviderBaseUrl}/v1/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${env.aiProviderApiKey}`,
    },
    body: JSON.stringify({
      stream: true,
      messages: [{ role: 'system', content: systemPrompt }, ...messages],
    }),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`AI provider stream request failed: ${response.status}`);
  }

  yield* parseSseStream(response, signal);
}

/** Consumes a full stream and returns the joined text — used for summarization. */
export async function collectAiReply(args) {
  let full = '';
  for await (const chunk of streamAiReply(args)) full += chunk;
  return full.trim();
}
