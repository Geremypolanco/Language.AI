import { useState } from 'react';
import { useVoiceConversation, isVoiceCallSupported } from '../../hooks/useVoiceConversation.js';
import { CallState } from '../../voice/index.js';
import VoiceStateOrb from './VoiceStateOrb.jsx';
import AIDisclaimer from '../AIDisclaimer.jsx';
import RateLimitAlert from '../RateLimitAlert.jsx';
import './VoiceCallScreen.css';

const MODES = [
  { value: 'general', label: 'Conversación general' },
  { value: 'language-learning', label: 'Práctica de idiomas' },
  { value: 'university', label: 'Tutor universitario' },
];

const LANGUAGES = [
  { value: 'es', label: 'Español' },
  { value: 'en', label: 'English' },
  { value: 'fr', label: 'Français' },
  { value: 'pt', label: 'Português' },
];

const CALL_ACTIVE_STATES = [
  CallState.REQUESTING_PERMISSION,
  CallState.LISTENING,
  CallState.THINKING,
  CallState.SPEAKING,
  CallState.INTERRUPTED,
  CallState.RECONNECTING,
];

export default function VoiceCallScreen() {
  const [mode, setMode] = useState('general');
  const [language, setLanguage] = useState('es');
  const { state, start, stop, transcript, errorMessage, volume, rateLimitInfo } = useVoiceConversation({
    mode,
    language,
  });

  const supported = isVoiceCallSupported();
  const isActive = CALL_ACTIVE_STATES.includes(state);
  const lastCaption = transcript[transcript.length - 1];

  if (!supported) {
    return (
      <div className="voice-call-screen">
        <p className="voice-call-screen__unsupported">
          Tu navegador no soporta reconocimiento o síntesis de voz. Prueba con Google Chrome o Microsoft Edge.
        </p>
      </div>
    );
  }

  if (!isActive) {
    return (
      <div className="voice-call-screen voice-call-screen--setup">
        <h1 className="voice-call-screen__title">Conversación por voz</h1>
        <p className="voice-call-screen__subtitle">Habla con la IA como si fuera una llamada telefónica.</p>

        <div className="voice-call-screen__options">
          <label>
            Modo
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              {MODES.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Idioma
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <button type="button" className="voice-call-screen__start-btn" onClick={start}>
          Start Conversation
        </button>

        {errorMessage && <p className="voice-call-screen__error">{errorMessage}</p>}
        <AIDisclaimer />
      </div>
    );
  }

  return (
    <div className="voice-call-screen voice-call-screen--in-call">
      <VoiceStateOrb state={state} volume={volume} />

      {lastCaption && (
        <p className="voice-call-screen__caption" aria-live="polite">
          {lastCaption.text}
        </p>
      )}

      {rateLimitInfo && (
        <RateLimitAlert secondsRemaining={rateLimitInfo.retryAfterSeconds} />
      )}

      <button type="button" className="voice-call-screen__end-btn" onClick={stop}>
        Finalizar llamada
      </button>

      <AIDisclaimer />
    </div>
  );
}
