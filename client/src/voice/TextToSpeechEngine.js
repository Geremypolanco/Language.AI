export function isSpeechSynthesisSupported() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

/**
 * Thin wrapper around the browser's SpeechSynthesis (TTS) exposing a small,
 * stable interface (speak/cancel/isSpeaking) instead of the Web Speech API
 * directly. Successive speak() calls are naturally queued by the browser and
 * play back-to-back — the engine uses this to start speaking the first
 * sentence of a reply while later sentences are still streaming in.
 * cancel() clears the *entire* pending queue at once, which is exactly the
 * primitive barge-in needs.
 *
 * Swap this class for a cloud TTS (ElevenLabs, etc.) that streams real audio
 * through AudioPlayback.js without touching the conversation orchestrator.
 */
export class TextToSpeechEngine {
  #pendingCount = 0;

  constructor({ language = 'en-US', rate = 1, onQueueStart, onQueueEmpty, onError } = {}) {
    this.language = language;
    this.rate = rate;
    this.onQueueStart = onQueueStart;
    this.onQueueEmpty = onQueueEmpty;
    this.onError = onError;
  }

  setLanguage(language) {
    this.language = language;
  }

  setRate(rate) {
    this.rate = rate;
  }

  /** Enqueues a chunk of text to be spoken after anything already queued. */
  speak(text) {
    if (!text?.trim()) return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = this.language;
    utterance.rate = this.rate;

    this.#pendingCount += 1;
    if (this.#pendingCount === 1) this.onQueueStart?.();

    utterance.onend = () => this.#onUtteranceSettled();
    utterance.onerror = (event) => {
      if (event.error !== 'interrupted' && event.error !== 'canceled') this.onError?.(event.error);
      this.#onUtteranceSettled();
    };

    window.speechSynthesis.speak(utterance);
  }

  #onUtteranceSettled() {
    this.#pendingCount = Math.max(0, this.#pendingCount - 1);
    if (this.#pendingCount === 0) this.onQueueEmpty?.();
  }

  isSpeaking() {
    return this.#pendingCount > 0;
  }

  /** Immediately stops any currently-speaking utterance and clears the queue — the barge-in primitive. */
  cancel() {
    const wasPending = this.#pendingCount > 0;
    this.#pendingCount = 0;
    if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
      window.speechSynthesis.cancel();
    }
    if (wasPending) this.onQueueEmpty?.();
  }
}
