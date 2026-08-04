/**
 * Voice Conversation Engine call states — the single source of truth the UI
 * renders from. Keeping this list flat (no nested/derived state) is what
 * lets the call screen stay "just an animation of the current state".
 */
export const CallState = Object.freeze({
  IDLE: 'idle',
  REQUESTING_PERMISSION: 'requesting_permission',
  LISTENING: 'listening',
  THINKING: 'thinking',
  SPEAKING: 'speaking',
  INTERRUPTED: 'interrupted',
  RECONNECTING: 'reconnecting',
  DISCONNECTED: 'disconnected',
  ENDED: 'ended',
  ERROR: 'error',
});
