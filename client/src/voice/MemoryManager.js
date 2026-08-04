/**
 * Client-side transcript cache used for UI captions and the "repite" voice
 * command. The server is the source of truth for the conversation memory the
 * LLM actually sees (including summarization of long sessions); this is a
 * lightweight, capped mirror so the UI list never grows unbounded during a
 * very long call.
 */
export class MemoryManager {
  #entries = [];
  #maxEntries;

  constructor({ maxEntries = 100 } = {}) {
    this.#maxEntries = maxEntries;
  }

  add(role, text) {
    this.#entries.push({ role, text, ts: Date.now() });
    if (this.#entries.length > this.#maxEntries) this.#entries.shift();
  }

  getAll() {
    return [...this.#entries];
  }

  getLastByRole(role) {
    for (let i = this.#entries.length - 1; i >= 0; i--) {
      if (this.#entries[i].role === role) return this.#entries[i];
    }
    return null;
  }

  clear() {
    this.#entries = [];
  }
}
