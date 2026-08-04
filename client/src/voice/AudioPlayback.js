/**
 * Interruptible playback queue for streamed audio bytes (Blob/ArrayBuffer
 * chunks), independent from the text-to-speech engine that produces them.
 *
 * The current build speaks via the browser's SpeechSynthesis, which handles
 * its own audio output internally, so this class isn't on that path today.
 * It exists as the drop-in playback primitive for when TextToSpeechEngine is
 * swapped for a cloud TTS that returns real audio: that implementation
 * decodes/queues chunks through here instead of through
 * `window.speechSynthesis`, while the rest of the engine (barge-in,
 * state machine) stays unchanged because both expose the same
 * speak/cancel/isSpeaking-shaped surface.
 */
export class AudioPlayback {
  #audioContext = null;
  #queue = [];
  #currentSource = null;
  #playing = false;

  constructor({ onQueueStart, onQueueEmpty, onError } = {}) {
    this.onQueueStart = onQueueStart;
    this.onQueueEmpty = onQueueEmpty;
    this.onError = onError;
  }

  #ensureContext() {
    if (!this.#audioContext) {
      const AudioContextImpl = window.AudioContext || window.webkitAudioContext;
      this.#audioContext = new AudioContextImpl();
    }
    return this.#audioContext;
  }

  /** Enqueues a raw audio buffer to play after anything already queued. */
  async enqueue(arrayBuffer) {
    try {
      const ctx = this.#ensureContext();
      const audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0));
      this.#queue.push(audioBuffer);
      if (!this.#playing) this.#playNext();
    } catch (err) {
      this.onError?.(err);
    }
  }

  #playNext() {
    const next = this.#queue.shift();
    if (!next) {
      this.#playing = false;
      this.onQueueEmpty?.();
      return;
    }
    if (!this.#playing) this.onQueueStart?.();
    this.#playing = true;

    const source = this.#audioContext.createBufferSource();
    source.buffer = next;
    source.connect(this.#audioContext.destination);
    source.onended = () => this.#playNext();
    this.#currentSource = source;
    source.start();
  }

  isPlaying() {
    return this.#playing;
  }

  /** Immediately stops playback and drops everything queued — the barge-in primitive. */
  cancel() {
    this.#queue = [];
    try {
      this.#currentSource?.stop();
    } catch {
      // Already stopped/ended — safe to ignore.
    }
    this.#currentSource = null;
    if (this.#playing) {
      this.#playing = false;
      this.onQueueEmpty?.();
    }
  }
}
