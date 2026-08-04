const SENTENCE_END_RE = /[.!?…]+\s*$/;

/**
 * Accumulates streamed text tokens and flushes complete sentences so TTS can
 * start speaking the first sentence while later tokens are still arriving.
 * This is most of what makes a reply feel low-latency instead of waiting for
 * the full response before any audio plays.
 */
export class SentenceChunker {
  #buffer = '';

  /** Returns a completed sentence if the buffer now ends one, else null. */
  push(token) {
    this.#buffer += token;
    if (SENTENCE_END_RE.test(this.#buffer.trim())) {
      const sentence = this.#buffer.trim();
      this.#buffer = '';
      return sentence;
    }
    return null;
  }

  /** Returns and clears whatever is left in the buffer (call at stream end). */
  flush() {
    const rest = this.#buffer.trim();
    this.#buffer = '';
    return rest || null;
  }
}
