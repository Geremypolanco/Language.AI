/**
 * Energy-based Voice Activity Detection over the raw microphone stream.
 * Runs continuously for the whole call — including while the AI is
 * speaking — so it doubles as the barge-in detector: the engine treats a
 * speech-start event while state is "speaking" as an interruption.
 *
 * This is intentionally a lightweight RMS-threshold detector so the module
 * has no external dependency. Swap it for a model-based VAD (e.g. Silero)
 * behind the same {onSpeechStart, onSpeechEnd, onVolume} interface if
 * higher accuracy in noisy environments is needed later.
 */
export class VoiceActivityDetector {
  #audioContext = null;
  #analyser = null;
  #source = null;
  #dataArray = null;
  #rafId = null;
  #speaking = false;
  #silenceStartedAt = null;
  #speechStartedAt = null;

  constructor({
    speechThreshold = 0.02,
    silenceDurationMs = 700,
    minSpeechDurationMs = 200,
    onSpeechStart,
    onSpeechEnd,
    onVolume,
  } = {}) {
    this.speechThreshold = speechThreshold;
    this.silenceDurationMs = silenceDurationMs;
    this.minSpeechDurationMs = minSpeechDurationMs;
    this.onSpeechStart = onSpeechStart;
    this.onSpeechEnd = onSpeechEnd;
    this.onVolume = onVolume;
  }

  start(stream) {
    const AudioContextImpl = window.AudioContext || window.webkitAudioContext;
    this.#audioContext = new AudioContextImpl();
    this.#source = this.#audioContext.createMediaStreamSource(stream);
    this.#analyser = this.#audioContext.createAnalyser();
    this.#analyser.fftSize = 512;
    this.#analyser.smoothingTimeConstant = 0.4;
    this.#source.connect(this.#analyser);
    this.#dataArray = new Uint8Array(this.#analyser.frequencyBinCount);
    this.#loop();
  }

  #loop = () => {
    this.#analyser.getByteTimeDomainData(this.#dataArray);

    let sumSquares = 0;
    for (let i = 0; i < this.#dataArray.length; i++) {
      const normalized = (this.#dataArray[i] - 128) / 128;
      sumSquares += normalized * normalized;
    }
    const rms = Math.sqrt(sumSquares / this.#dataArray.length);
    this.onVolume?.(rms);

    const now = performance.now();
    if (rms > this.speechThreshold) {
      this.#silenceStartedAt = null;
      if (!this.#speaking) {
        this.#speaking = true;
        this.#speechStartedAt = now;
        this.onSpeechStart?.();
      }
    } else if (this.#speaking) {
      if (this.#silenceStartedAt === null) this.#silenceStartedAt = now;
      if (now - this.#silenceStartedAt >= this.silenceDurationMs) {
        const duration = now - this.#speechStartedAt;
        this.#speaking = false;
        this.#silenceStartedAt = null;
        if (duration >= this.minSpeechDurationMs) this.onSpeechEnd?.();
      }
    }

    this.#rafId = requestAnimationFrame(this.#loop);
  };

  isSpeaking() {
    return this.#speaking;
  }

  stop() {
    if (this.#rafId) cancelAnimationFrame(this.#rafId);
    this.#rafId = null;
    this.#source?.disconnect();
    this.#audioContext?.close().catch(() => {});
    this.#speaking = false;
    this.#silenceStartedAt = null;
  }
}
