import { useCallback, useState } from 'react';
import { apiFetch, RateLimitError } from '../utils/api.js';
import { useRateLimit } from './useRateLimit.js';

export function useAiChat() {
  const [messages, setMessages] = useState([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const rateLimit = useRateLimit();

  const sendMessage = useCallback(
    async (text, conversationId) => {
      setError(null);
      if (rateLimit.isLimited) return;

      setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'user', text }]);
      setSending(true);
      try {
        const data = await apiFetch('/ai/chat', {
          method: 'POST',
          body: JSON.stringify({ message: text, conversationId }),
        });
        setMessages((prev) => [
          ...prev,
          {
            id: data.messageId,
            role: 'assistant',
            text: data.reply,
            confidence: data.confidence,
            flagged: data.flagged,
            citations: data.citations,
          },
        ]);
        return data;
      } catch (err) {
        if (err instanceof RateLimitError) {
          rateLimit.start(err.retryAfterSeconds);
        } else {
          setError(err.message);
        }
      } finally {
        setSending(false);
      }
    },
    [rateLimit]
  );

  return { messages, sendMessage, sending, error, rateLimit };
}
