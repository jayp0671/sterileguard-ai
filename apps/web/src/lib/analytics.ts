import { currentConsent, gpcEnabled } from "@/lib/consent";

/**
 * PostHog is loaded only after analytics consent (SG-25): no script tag, no request to the
 * PostHog host before that. It is not configured in this prototype yet (no key), so today this
 * never loads anything; the gate is what the SG-26 privacy journey checks.
 */
export const POSTHOG_KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY ?? "";
export const POSTHOG_HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com";

let loaded = false;

export function analyticsAllowed(): boolean {
  return Boolean(currentConsent()?.analytics) && !gpcEnabled();
}

export function maybeLoadAnalytics(): boolean {
  if (loaded || !POSTHOG_KEY || !analyticsAllowed()) return false;
  const script = document.createElement("script");
  script.async = true;
  script.src = `${POSTHOG_HOST.replace(/\/$/, "")}/static/array.js`;
  script.dataset.key = POSTHOG_KEY;
  document.head.appendChild(script);
  loaded = true;
  return true;
}
