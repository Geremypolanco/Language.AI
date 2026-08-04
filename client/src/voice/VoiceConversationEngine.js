import { CallState } from './constants.js';
import { MicrophoneManager } from './MicrophoneManager.js';
import { VoiceActivityDetector } from './VoiceActivityDetector.js';
import { SpeechRecognizer, isSpeechRecognitionSupported } from './SpeechRecognizer.js';
import { TextToSpeechEngine, isSpeechSynthesisSupported } from './TextToSpeechEngine.js';
import { LLMConnector, RateLimitError, SessionExpiredError, InputRejectedError } from './LLMConnector.js';
import { SessionManager } from './SessionManager.js';
import { MemoryManager } from './MemoryManager.js';
import { SentenceChunker } from './sentenceChunker.js';
import { detectLanguage, localeForLanguageCode } from './languageDetect.js';

const STOP_COMMANDS = ['espera', 'detente', 'para', 'stop', 'wait', 'cancela', 'cancel'];
const REPEAT_COMMANDS = ['repite', 'repitelo', 'repeat', 'repeat that'];
const CONTINUE_COMMANDS = ['continua', 'sigue', 'continue', 'go on'];
const BARGE_IN_GRACE_MS = 300; // ignore VAD triggers just after TTS starts (onset pop / self-trigger)
const INTERRUPTED_FLASH_MS = 400; // how long the "Interrupted" state is shown before returning to Listening

const COMBINING_DIACRITICS_RE = new RegExp('[\\u0300-\\u036f]', 'g');

function normalizeCommand(text) {
  return text
    .toLowerCase()
    .normalize('NFD')
    .replace(COMBINING_DIACRITICS_RE, '')
    .replace(/[^\w\s]/g, '')
    .trim();
}

function matchesCommand(text, phrases) {
  const normalized = normalizeCommand(text);
  if (!normalized || normalized.split(/\s+/).length > 4) return false;
  return phrases.includes(normalized);
}

class Emitter {
  #listeners = new Map();

  on(event, fn) {
    if (!this.#listeners.has(event)) this.#listeners.set(event, new Set());
    this.#listeners.get(event).add(fn);
    return () => this.off(event, fn);
  }

  off(event, fn) {
    this.#listeners.get(event)?.delete(fn);
  }

  emit(event, payload) {
    this.#listeners.get(event)?.forEach((fn) => fn(payload));
  }
}

/**
 * Orchestrates every module into one continuous, hands-free call:
 * mic -> VAD -> STT -> (this) -> LLM -> TTS -> audio -> back to listening.
 * This is the only class the UI talks to; every other file in this module
 * is a decoupled implementation detail behind a narrow interface, swappable
 * (cloud STT/TTS, WebRTC transport, video) without changing this state
 * machine's shape.
 */
export class VoiceConversationEngine extends Emitter {
  #mic = new MicrophoneManager();
  #vad = null;
  #recognizer = null;
  #tts = null;
  #connector = new LLMConnector();
  #sessionManager = new SessionManager(this.#connector);
  #memory = new MemoryManager();

  #state = CallState.IDLE;
  #session = null;
  #languageCode;
  #mode;
  #personality;
  #ttsStartedAt = 0;
  #stopped = true;

  constructor({ mode = 'general', language = 'es', personality } = {}) {
    super();
    this.#mode = mode;
    this.#languageCode = language;
    this.#personality = personality;
  }

  getState() {
    return this.#state;
  }

  getMode() {
    return this.#mode;
  }

  getLanguage() {
    return this.#languageCode;
  }

  getTranscript() {
    return this.#memory.getAll();
  }

  isSupported() {
    return isSpeechRecognitionSupported() && isSpeechSynthesisSupported();
  }

  #setState(state, extra) {
    this.#state = state;
    this.emit('state', { state, ...extra });
  }

  async start() {
    if (!this.isSupported()) {
      this.#setState(CallState.ERROR, { message: 'Este navegador no soporta reconocimiento o síntesis de voz.' });
      return;
    }

    this.#stopped = false;
    this.#setState(CallState.REQUESTING_PERMISSION);

    let stream;
    try {
      stream = await this.#mic.requestAccess();
    } catch {
      this.#setState(CallState.ERROR, { message: 'Acceso al micrófono denegado.' });
      this.#stopped = true;
      return;
    }
    if (this.#stopped) return; // stop() was called while awaiting the permission prompt

    this.#vad = new VoiceActivityDetector({
      onSpeechStart: () => this.#handleSpeechStart(),
      onSpeechEnd: () => this.#handleSpeechEnd(),
      onVolume: (level) => this.emit('volume', level),
    });
    this.#vad.start(stream);

    this.#tts = new TextToSpeechEngine({
      language: localeForLanguageCode(this.#languageCode),
      onQueueEmpty: () => this.#handleTtsQueueEmpty(),
      onError: (err) => console.error('[voice] TTS error', err),
    });

    this.#recognizer = new SpeechRecognizer({
      language: localeForLanguageCode(this.#languageCode),
      onInterimResult: (text) => this.emit('transcript', { role: 'user', text, final: false }),
      onFinalResult: (text) => this.#handleUserUtterance(text),
      onError: (error) => this.#handleRecognizerError(error),
      onEnd: () => this.#handleRecognizerEnd(),
    });

    try {
      await this.#establishSession();
    } catch (err) {
      console.error('[voice] failed to establish session', err);
      this.#setState(CallState.ERROR, { message: 'No se pudo iniciar la conversación.' });
      this.#stopped = true;
      this.#mic.release();
      this.#vad.stop();
      return;
    }
    if (this.#stopped) return;

    this.#recognizer.start();
    this.#setState(CallState.LISTENING);
  }

  async #establishSession() {
    const restored = await this.#sessionManager.restore();
    if (restored) {
      this.#session = restored;
      this.#mode = restored.mode;
      this.#languageCode = restored.language;
      return;
    }
    const created = await this.#connector.createSession({
      mode: this.#mode,
      language: this.#languageCode,
      personality: this.#personality,
    });
    this.#session = created;
    this.#sessionManager.save(created);
  }

  // --- Barge-in -------------------------------------------------------

  #handleSpeechStart() {
    const isBargeIn = this.#state === CallState.SPEAKING && performance.now() - this.#ttsStartedAt > BARGE_IN_GRACE_MS;
    if (!isBargeIn) return;

    this.#setState(CallState.INTERRUPTED);
    this.#tts.cancel();
    this.#connector.interrupt();
    setTimeout(() => {
      if (this.#state === CallState.INTERRUPTED) this.#setState(CallState.LISTENING);
    }, INTERRUPTED_FLASH_MS);
  }

  #handleSpeechEnd() {
    // Native STT finality (onFinalResult) is the primary turn-taking
    // trigger today. VAD-based silence detection is kept wired for future
    // STT backends (e.g. streaming Whisper) that don't self-endpoint and
    // need an external signal for "the user stopped talking".
  }

  #handleTtsQueueEmpty() {
    if (this.#state === CallState.SPEAKING) this.#setState(CallState.LISTENING);
  }

  #handleRecognizerError(error) {
    if (error === 'not-allowed' || error === 'service-not-allowed') {
      this.#setState(CallState.ERROR, { message: 'Permiso de micrófono revocado.' });
      this.stop();
      return;
    }
    console.warn('[voice] recognizer error', error);
  }

  #handleRecognizerEnd() {
    // Browsers stop continuous recognition after periods of inactivity —
    // restart it so the mic stays "always on" for the rest of the call.
    if (this.#stopped) return;
    if ([CallState.ENDED, CallState.DISCONNECTED, CallState.ERROR].includes(this.#state)) return;
    setTimeout(() => {
      if (!this.#stopped) this.#recognizer?.start();
    }, 150);
  }

  // --- Turn handling ----------------------------------------------------

  async #handleUserUtterance(text) {
    if (!text || this.#stopped) return;

    if (matchesCommand(text, STOP_COMMANDS)) {
      this.#tts?.cancel();
      this.#connector.interrupt();
      this.#setState(CallState.LISTENING);
      return;
    }
    if (matchesCommand(text, REPEAT_COMMANDS)) {
      const last = this.#memory.getLastByRole('assistant');
      if (last) {
        this.#setState(CallState.SPEAKING);
        this.#ttsStartedAt = performance.now();
        this.#tts.speak(last.text);
      }
      return;
    }
    if (matchesCommand(text, CONTINUE_COMMANDS) && this.#state !== CallState.LISTENING) {
      this.#setState(CallState.LISTENING);
      return;
    }

    this.emit('transcript', { role: 'user', text, final: true });
    this.#memory.add('user', text);
    await this.#sendTurn(text);
  }

  async #sendTurn(text) {
    this.#setState(CallState.THINKING);

    const detected = detectLanguage(text);
    if (detected && detected.code !== this.#languageCode) {
      this.setLanguage(detected.code);
    }

    const chunker = new SentenceChunker();
    let spokeFirstSentence = false;
    let fullReply = '';

    const beginSpeaking = () => {
      spokeFirstSentence = true;
      this.#setState(CallState.SPEAKING);
      this.#ttsStartedAt = performance.now();
    };

    const onDelta = (delta) => {
      fullReply += delta;
      this.emit('transcript', { role: 'assistant', text: fullReply, final: false });
      const sentence = chunker.push(delta);
      if (sentence) {
        if (!spokeFirstSentence) beginSpeaking();
        this.#tts.speak(sentence);
      }
    };

    try {
      const result = await this.#connector.converse(
        { sessionId: this.#session.sessionId, message: text, language: this.#languageCode },
        { onDelta }
      );

      const remainder = chunker.flush();
      if (remainder) {
        if (!spokeFirstSentence) beginSpeaking();
        this.#tts.speak(remainder);
      }

      if (!result.interrupted && fullReply.trim()) {
        this.emit('transcript', { role: 'assistant', text: fullReply.trim(), final: true });
        this.#memory.add('assistant', fullReply.trim());
      }
      if (result.flagged) this.emit('flagged', { text: fullReply.trim() });

      // Nothing was ever queued for TTS (e.g. instantly interrupted) — go straight back to listening.
      if (!spokeFirstSentence) this.#setState(CallState.LISTENING);
    } catch (err) {
      await this.#handleTurnError(err);
    }
  }

  async #handleTurnError(err) {
    if (err instanceof RateLimitError) {
      this.emit('rateLimited', { retryAfterSeconds: err.retryAfterSeconds });
      this.#setState(CallState.LISTENING);
      return;
    }
    if (err instanceof InputRejectedError) {
      this.#setState(CallState.SPEAKING);
      this.#ttsStartedAt = performance.now();
      this.#tts.speak('Lo siento, no puedo responder a eso. ¿Puedes reformularlo?');
      return;
    }
    if (err instanceof SessionExpiredError) {
      try {
        const created = await this.#connector.createSession({
          mode: this.#mode,
          language: this.#languageCode,
          personality: this.#personality,
        });
        this.#session = created;
        this.#sessionManager.save(created);
        this.#memory.clear();
      } catch {
        // Session recreation failed too — fall through to listening; the
        // next utterance will retry establishing a session.
      }
      this.#setState(CallState.LISTENING);
      return;
    }

    console.error('[voice] turn failed, attempting to reconnect', err);
    this.#setState(CallState.RECONNECTING);
    try {
      await this.#sessionManager.withRetry(async () => {
        const remote = await this.#connector.getSession(this.#session.sessionId);
        if (!remote) throw new Error('session no longer exists');
        return remote;
      });
      this.#setState(CallState.LISTENING);
    } catch {
      this.#setState(CallState.DISCONNECTED, { message: 'No se pudo restablecer la conexión.' });
    }
  }

  // --- Public controls ----------------------------------------------------

  setLanguage(languageCode) {
    this.#languageCode = languageCode;
    this.#recognizer?.setLanguage(localeForLanguageCode(languageCode));
    this.#tts?.setLanguage(localeForLanguageCode(languageCode));
  }

  stop() {
    this.#stopped = true;
    this.#tts?.cancel();
    this.#connector.interrupt();
    this.#vad?.stop();
    this.#recognizer?.abort();
    this.#mic.release();
    if (this.#session) this.#connector.endSession(this.#session.sessionId);
    this.#sessionManager.clear();
    this.#memory.clear();
    this.#setState(CallState.ENDED);
  }
}
