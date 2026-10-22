"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";

/** Plan §9.2: sign out after 15 minutes idle, with a 60-second warning at 14 minutes. */
export const IDLE_TIMEOUT_MS = 15 * 60 * 1000;
export const IDLE_WARNING_MS = 60 * 1000;

const ACTIVITY_EVENTS = ["pointerdown", "pointermove", "keydown", "wheel", "touchstart"] as const;

export type IdleState = {
  /** True while the warning modal should be shown. */
  warning: boolean;
  /** Whole seconds left before sign-out, while warning. */
  secondsLeft: number;
  /** "Stay signed in": resets the timer (caller also refreshes the session). */
  stay: () => void;
};

export function useIdleTimeout(
  onTimeout: () => void,
  { timeoutMs = IDLE_TIMEOUT_MS, warningMs = IDLE_WARNING_MS, enabled = true } = {},
): IdleState {
  const lastActivity = useRef(Date.now());
  const [now, setNow] = useState(() => Date.now());
  // Forces a render when stay() resets the timer within the same clock tick.
  const [, rerender] = useReducer((n: number) => n + 1, 0);
  const fired = useRef(false);
  const onTimeoutRef = useRef(onTimeout);
  onTimeoutRef.current = onTimeout;

  const remaining = timeoutMs - (now - lastActivity.current);
  const warning = enabled && remaining <= warningMs && remaining > 0;

  const stay = useCallback(() => {
    lastActivity.current = Date.now();
    fired.current = false;
    setNow(Date.now());
    rerender();
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const onActivity = () => {
      // Activity during the warning does not dismiss it: the user must choose "Stay signed in".
      const left = timeoutMs - (Date.now() - lastActivity.current);
      if (left > warningMs) lastActivity.current = Date.now();
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") setNow(Date.now());
    };
    for (const e of ACTIVITY_EVENTS) window.addEventListener(e, onActivity, { passive: true });
    document.addEventListener("visibilitychange", onVisibility);
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      for (const e of ACTIVITY_EVENTS) window.removeEventListener(e, onActivity);
      document.removeEventListener("visibilitychange", onVisibility);
      window.clearInterval(tick);
    };
  }, [enabled, timeoutMs, warningMs]);

  useEffect(() => {
    if (enabled && remaining <= 0 && !fired.current) {
      fired.current = true;
      onTimeoutRef.current();
    }
  }, [enabled, remaining]);

  return { warning, secondsLeft: Math.max(0, Math.ceil(remaining / 1000)), stay };
}
