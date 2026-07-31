import { useState } from 'react';
import { apiFetch } from '../utils/api.js';
import './ChatFeedback.css';

export default function ChatFeedback({ messageId, conversationId }) {
  const [rating, setRating] = useState(null);
  const [showReportForm, setShowReportForm] = useState(false);
  const [reportReason, setReportReason] = useState('');
  const [submitted, setSubmitted] = useState(false);

  async function sendFeedback(payload) {
    try {
      await apiFetch('/feedback', { method: 'POST', body: JSON.stringify(payload) });
      setSubmitted(true);
    } catch {
      // Best-effort UI feedback signal; a failed submission isn't worth blocking the user.
    }
  }

  function handleRate(value) {
    setRating(value);
    sendFeedback({ messageId, conversationId, rating: value });
  }

  function handleReportSubmit(e) {
    e.preventDefault();
    sendFeedback({ messageId, conversationId, reportReason });
    setShowReportForm(false);
  }

  if (submitted && !showReportForm) {
    return <p className="chat-feedback__thanks">Gracias por tu retroalimentación.</p>;
  }

  return (
    <div className="chat-feedback">
      <div className="chat-feedback__buttons">
        <button
          type="button"
          aria-label="Respuesta útil"
          className={`chat-feedback__btn ${rating === 'up' ? 'chat-feedback__btn--active' : ''}`}
          onClick={() => handleRate('up')}
        >
          👍
        </button>
        <button
          type="button"
          aria-label="Respuesta no útil"
          className={`chat-feedback__btn ${rating === 'down' ? 'chat-feedback__btn--active' : ''}`}
          onClick={() => handleRate('down')}
        >
          👎
        </button>
        <button type="button" className="chat-feedback__report-link" onClick={() => setShowReportForm((s) => !s)}>
          Reportar error
        </button>
      </div>

      {showReportForm && (
        <form className="chat-feedback__form" onSubmit={handleReportSubmit}>
          <textarea
            placeholder="Describe el problema con esta respuesta (información incorrecta, sesgo, contenido inapropiado...)"
            value={reportReason}
            onChange={(e) => setReportReason(e.target.value)}
            maxLength={1000}
            required
          />
          <button type="submit" className="chat-feedback__submit">
            Enviar reporte
          </button>
        </form>
      )}
    </div>
  );
}
