const PERMISSION_FLAG_KEY = 'languageai_mic_permission_granted';

/**
 * Owns getUserMedia lifecycle. The browser itself only ever prompts once per
 * origin for microphone access; this class just avoids the app *asking* the
 * user again once we know it was already granted (permissions.query when
 * available, a local hint otherwise), and centralizes stream teardown so a
 * stray track doesn't keep the mic indicator on after a call ends.
 */
export class MicrophoneManager {
  #stream = null;

  async hasPermission() {
    if (navigator.permissions?.query) {
      try {
        const status = await navigator.permissions.query({ name: 'microphone' });
        return status.state === 'granted';
      } catch {
        // Some browsers don't support querying 'microphone' — fall through to the local hint.
      }
    }
    return localStorage.getItem(PERMISSION_FLAG_KEY) === 'true';
  }

  async requestAccess() {
    if (this.#stream) return this.#stream;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    this.#stream = stream;
    localStorage.setItem(PERMISSION_FLAG_KEY, 'true');
    return stream;
  }

  getStream() {
    return this.#stream;
  }

  release() {
    this.#stream?.getTracks().forEach((track) => track.stop());
    this.#stream = null;
  }
}
