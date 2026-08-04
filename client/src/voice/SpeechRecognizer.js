const SpeechRecognitionImpl =
  typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : null;

export function isSpeechRecognitionSupported() {
  return Boolean(SpeechRecognitionImpl);
}

/**
 * Thin wrapper around the browser's native SpeechRecognition (STT) so the
 * rest of the engine depends on a small, stable interface
 * (start/stop/onInterimResult/onFinalResult) instead of the vendor-prefixed
 * Web Speech API. Swap this class for a cloud streaming STT client
 * (Deepgram, streaming Whisper, etc.) without touching the conversation
 * orchestrator — the interface stays the same.
 *
 * `continuous: true` keeps listening across utterances, but Chrome still
 * ends the session after a period of silence/inactivity; the engine is
 * expected to call start() again from onEnd to keep the mic "always on"
 * for the duration of the call.
 */
export class SpeechRecognizer {
  #recognition = null;
  #active = false;

  constructor({ language = 'en-US', onInterimResult, onFinalResult, onError, onEnd } = {}) {
    if (!SpeechRecognitionImpl) {
      throw new Error('SpeechRecognition is not supported in this browser.');
    }
    this.language = language;
    this.onInterimResult = onInterimResult;
    this.onFinalResult = onFinalResult;
    this.onError = onError;
    this.onEnd = onEnd;
  }

  #createRecognition() {
    const recognition = new SpeechRecognitionImpl();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = this.language;

    recognition.onresult = (event) => {
      let interim = '';
      let final = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) final += result[0].transcript;
        else interim += result[0].transcript;
      }
      if (interim) this.onInterimResult?.(interim);
      if (final.trim()) this.onFinalResult?.(final.trim());
    };

    recognition.onerror = (event) => {
      // 'no-speech' and 'aborted' happen routinely during normal silence/teardown.
      if (event.error !== 'no-speech' && event.error !== 'aborted') {
        this.onError?.(event.error);
      }
    };

    recognition.onend = () => {
      this.#active = false;
      this.onEnd?.();
    };

    return recognition;
  }

  setLanguage(language) {
    if (this.language === language) return;
    this.language = language;
    if (this.#active) {
      this.stop();
      this.start();
    }
  }

  start() {
    if (this.#active) return;
    this.#recognition = this.#createRecognition();
    try {
      this.#recognition.start();
      this.#active = true;
    } catch {
      // start() throws if called while already starting — safe to ignore, onend will retry.
    }
  }

  stop() {
    this.#active = false;
    this.#recognition?.stop();
  }

  abort() {
    this.#active = false;
    this.#recognition?.abort();
  }

  isActive() {
    return this.#active;
  }
}
