import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Tracks a rate-limit cooldown countdown. Call start(seconds) when a 429 is
 * received; the hook exposes secondsRemaining ticking down to 0 and
 * isLimited so the UI can disable input and show a live countdown.
 */
export function useRateLimit() {
  const [secondsRemaining, setSecondsRemaining] = useState(0);
  const intervalRef = useRef(null);

  const start = useCallback((seconds) => {
    setSecondsRemaining(seconds);
  }, []);

  useEffect(() => {
    if (secondsRemaining <= 0) {
      clearInterval(intervalRef.current);
      return;
    }
    intervalRef.current = setInterval(() => {
      setSecondsRemaining((s) => Math.max(0, s - 1));
    }, 1000);
    return () => clearInterval(intervalRef.current);
  }, [secondsRemaining > 0]);

  return { secondsRemaining, isLimited: secondsRemaining > 0, start };
}
