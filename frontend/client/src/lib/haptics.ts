// Subtle vibration feedback for mobile — the Vibration API is Android-
// Chrome-class browsers only (iOS Safari has never implemented it), so
// every call here is a no-op there rather than an error. Patterns are
// short and light on purpose: this is a physical accent on top of the
// visual/audio feedback that already exists, not a replacement for it.
function vibrate(pattern: number | number[]): void {
  if (typeof navigator !== "undefined" && "vibrate" in navigator) {
    try {
      navigator.vibrate(pattern);
    } catch {
      // Some browsers throw if called outside a user gesture — never let
      // a haptic nicety break the actual interaction it's attached to.
    }
  }
}

export const haptics = {
  correct: () => vibrate(30),
  incorrect: () => vibrate([25, 60, 25]),
  // A very light pulse for "the tutor is composing a reply" — subtle
  // enough not to feel like an alert, just a physical cue that something
  // is happening.
  thinking: () => vibrate(15),
};
