/**
 * Cookie consent (SG-25 Part C, plan §14.4). Essential cookies are always on; analytics are off
 * until the visitor opts in, and Global Privacy Control counts as an opt-out. The choice lives
 * in the `sg_consent` cookie (JSON: version, analytics, ts) and is logged to the API.
 */

export const CONSENT_VERSION = "1.0.0";
export const CONSENT_COOKIE = "sg_consent";
export const ANON_KEY = "sg_anon_id";
export const OPEN_SETTINGS_EVENT = "sg:cookie-settings";
const MAX_AGE_S = 365 * 24 * 3600;

export type Consent = { version: string; analytics: boolean; ts: string };

export function parseConsent(cookieHeader: string): Consent | null {
  const raw = cookieHeader
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith(`${CONSENT_COOKIE}=`));
  if (!raw) return null;
  try {
    const value = JSON.parse(decodeURIComponent(raw.slice(CONSENT_COOKIE.length + 1))) as Consent;
    if (typeof value.analytics !== "boolean" || typeof value.version !== "string") return null;
    return value;
  } catch {
    return null;
  }
}

/** The stored choice, if it was made for the current policy version. */
export function currentConsent(): Consent | null {
  if (typeof document === "undefined") return null;
  const c = parseConsent(document.cookie);
  return c && c.version === CONSENT_VERSION ? c : null;
}

export function gpcEnabled(): boolean {
  return (
    typeof navigator !== "undefined" &&
    (navigator as { globalPrivacyControl?: boolean }).globalPrivacyControl === true
  );
}

export function writeConsent(analytics: boolean, now = new Date()): Consent {
  const value: Consent = {
    version: CONSENT_VERSION,
    analytics: analytics && !gpcEnabled(),
    ts: now.toISOString(),
  };
  const secure =
    typeof location !== "undefined" && location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${CONSENT_COOKIE}=${encodeURIComponent(JSON.stringify(value))}; Max-Age=${MAX_AGE_S}; Path=/; SameSite=Lax${secure}`;
  return value;
}

export function anonId(): string {
  try {
    const have = window.localStorage.getItem(ANON_KEY);
    if (have) return have;
    const id = globalThis.crypto.randomUUID();
    window.localStorage.setItem(ANON_KEY, id);
    return id;
  } catch {
    return globalThis.crypto.randomUUID();
  }
}

export function openCookieSettings(): void {
  window.dispatchEvent(new Event(OPEN_SETTINGS_EVENT));
}
