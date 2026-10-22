"use client";

import Script from "next/script";
import { useEffect, useRef } from "react";

// Cloudflare's documented always-pass test key, used when no site key is configured (local dev).
const TEST_SITE_KEY = "1x00000000000000000000AA";

type TurnstileApi = {
  render: (el: HTMLElement, opts: Record<string, unknown>) => string;
  reset: (id?: string) => void;
  remove: (id: string) => void;
};

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

/** Cloudflare Turnstile widget. Supabase requires its token on sign-in, OTP and password reset. */
export function Turnstile({
  onToken,
  resetKey = 0,
}: {
  onToken: (token: string | null) => void;
  /** Change to force a fresh token (tokens are single use). */
  resetKey?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);
  const onTokenRef = useRef(onToken);
  onTokenRef.current = onToken;
  const siteKey = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || TEST_SITE_KEY;

  useEffect(() => {
    let cancelled = false;
    const mount = () => {
      if (cancelled || !ref.current || !window.turnstile) return false;
      if (widgetId.current) window.turnstile.remove(widgetId.current);
      onTokenRef.current(null);
      widgetId.current = window.turnstile.render(ref.current, {
        sitekey: siteKey,
        callback: (token: string) => onTokenRef.current(token),
        "expired-callback": () => onTokenRef.current(null),
        "error-callback": () => onTokenRef.current(null),
      });
      return true;
    };
    if (!mount()) {
      const timer = window.setInterval(() => {
        if (mount()) window.clearInterval(timer);
      }, 200);
      return () => {
        cancelled = true;
        window.clearInterval(timer);
      };
    }
    return () => {
      cancelled = true;
    };
  }, [siteKey, resetKey]);

  return (
    <>
      <Script
        src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"
        strategy="afterInteractive"
      />
      <div ref={ref} className="min-h-16" />
    </>
  );
}
