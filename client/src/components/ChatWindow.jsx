import { useState } from 'react';
import { useAiChat } from '../hooks/useAiChat.js';
import RateLimitAlert from './RateLimitAlert.jsx';
import AIDisclaimer from './AIDisclaimer.jsx';
import ChatFeedback from './ChatFeedback.jsx';
import './ChatWindow.css';

export default function ChatWindow() {
  const { messages, sendMessage, sending, error, rateLimit } = useAiChat();
  const [input, setInput] = useState('');
  const [conversationId, setConversationId] = useState(undefined);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!input.trim() || sending || rateLimit.isLimited) return;
    const text = input;
    setInput('');
    const result = await sendMessage(text, conversationId);
    if (result?.conversationId) setConversationId(result.conversationId);
  }

  return (
    <div className="chat-window">
      <div className="chat-window__messages">
        {messages.map((m) => (
          <div key={m.id} className={`chat-window__message chat-window__message--${m.role}`}>
            <p>{m.text}</p>
            {m.role === 'assistant' && (
              <>
                {m.flagged && <span className="chat-window__flag">⚠️ Verifica esta respuesta</span>}
                <ChatFeedback messageId={m.id} conversationId={conversationId} />
              </>
            )}
          </div>
        ))}
      </div>

      <RateLimitAlert secondsRemaining={rateLimit.secondsRemaining} />
      {error && <p className="chat-window__error">{error}</p>}

      <form className="chat-window__input-row" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Escribe tu mensaje..."
          disabled={sending || rateLimit.isLimited}
          maxLength={4000}
        />
        <button type="submit" disabled={sending || rateLimit.isLimited || !input.trim()}>
          Enviar
        </button>
      </form>

      <AIDisclaimer />
    </div>
  );
}
