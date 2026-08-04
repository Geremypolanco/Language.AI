import { CallState } from '../../voice/index.js';
import './VoiceStateOrb.css';

const STATE_LABELS = {
  [CallState.IDLE]: '',
  [CallState.REQUESTING_PERMISSION]: 'Solicitando micrófono…',
  [CallState.LISTENING]: 'Escuchando',
  [CallState.THINKING]: 'Pensando…',
  [CallState.SPEAKING]: 'Hablando',
  [CallState.INTERRUPTED]: 'Interrumpido',
  [CallState.RECONNECTING]: 'Reconectando…',
  [CallState.DISCONNECTED]: 'Desconectado',
  [CallState.ENDED]: 'Llamada finalizada',
  [CallState.ERROR]: 'Error',
};

export default function VoiceStateOrb({ state, volume = 0 }) {
  const scale = state === CallState.LISTENING ? 1 + Math.min(volume * 4, 0.35) : 1;

  return (
    <div className="voice-orb-wrapper">
      <div
        className={`voice-orb voice-orb--${state}`}
        style={{ transform: `scale(${scale})` }}
        aria-hidden="true"
      >
        <div className="voice-orb__core" />
        <div className="voice-orb__ring voice-orb__ring--1" />
        <div className="voice-orb__ring voice-orb__ring--2" />
      </div>
      <p className="voice-orb__label" role="status" aria-live="polite">
        {STATE_LABELS[state] ?? ''}
      </p>
    </div>
  );
}
