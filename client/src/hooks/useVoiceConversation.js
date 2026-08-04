import { useCallback, useEffect, useRef, useState } from 'react';
import {
  VoiceConversationEngine,
  CallState,
  isSpeechRecognitionSupported,
  isSpeechSynthesisSupported,
} from '../voice/index.js';

export const isVoiceCallSupported = () => isSpeechRecognitionSupported() && isSpeechSynthesisSupported();

/**
 * React binding for VoiceConversationEngine. The engine itself is plain JS
 * (framework-agnostic on purpose) — this hook just mirrors its events into
 * component state so VoiceCallScreen can render off of them.
 */
export function useVoiceConversation({ mode = 'general', language = 'es', personality } = {}) {
  const engineRef = useRef(null);
  const [state, setState] = useState(CallState.IDLE);
  const [errorMessage, setErrorMessage] = useState(null);
  const [transcript, setTranscript] = useState([]);
  const [volume, setVolume] = useState(0);
  const [rateLimitInfo, setRateLimitInfo] = useState(null);

  const ensureEngine = useCallback(() => {
    if (engineRef.current) return engineRef.current;

    const engine = new VoiceConversationEngine({ mode, language, personality });

    engine.on('state', ({ state: newState, message }) => {
      setState(newState);
      setErrorMessage(newState === CallState.ERROR || newState === CallState.DISCONNECTED ? message || null : null);
    });

    engine.on('transcript', (entry) => {
      setTranscript((prev) => {
        const last = prev[prev.length - 1];
        // Interim results replace the previous interim entry from the same speaker instead of piling up.
        if (last && last.role === entry.role && !last.final) return [...prev.slice(0, -1), entry];
        return [...prev, entry];
      });
    });

    engine.on('volume', setVolume);
    engine.on('rateLimited', setRateLimitInfo);

    engineRef.current = engine;
    return engine;
  }, [mode, language, personality]);

  const start = useCallback(() => {
    setTranscript([]);
    setErrorMessage(null);
    ensureEngine().start();
  }, [ensureEngine]);

  const stop = useCallback(() => {
    engineRef.current?.stop();
  }, []);

  const setLanguage = useCallback((languageCode) => {
    engineRef.current?.setLanguage(languageCode);
  }, []);

  useEffect(() => {
    if (!rateLimitInfo) return undefined;
    const timer = setTimeout(() => setRateLimitInfo(null), rateLimitInfo.retryAfterSeconds * 1000);
    return () => clearTimeout(timer);
  }, [rateLimitInfo]);

  // Ensure the mic/session are always released if the component unmounts mid-call.
  useEffect(() => () => engineRef.current?.stop(), []);

  return {
    state,
    start,
    stop,
    setLanguage,
    transcript,
    errorMessage,
    volume,
    rateLimitInfo,
  };
}
