/** Route-guard decisions for the proxy (plan §9.2). Pure, so every auth state is unit tested. */

export const PUBLIC_PATHS = [
  "/sign-in",
  "/magic-link",
  "/accept-invite",
  "/reset-password",
  "/auth",
  "/mfa",
  "/trust",
  "/status",
  "/.well-known",
] as const;

export const SESSION_LIMIT_MS = 12 * 60 * 60 * 1000;
export const SESSION_STARTED_COOKIE = "sg_session_started_at";

export type AuthState = {
  hasSession: boolean;
  /** Current assurance level of the session. */
  aal: "aal1" | "aal2" | null;
  /** "aal2" when the user has at least one verified factor (Supabase nextLevel). */
  nextLevel: "aal1" | "aal2" | null;
  /** ms epoch from the sg_session_started_at cookie, if present. */
  sessionStartedAt?: number | null;
  now?: number;
};

export type Decision = { type: "allow" } | { type: "redirect"; to: string; signOut?: boolean };

export function isPublicPath(pathname: string): boolean {
  if (pathname === "/") return true;
  return PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/** Only allow same-site relative `next` targets (no open redirects). */
export function safeNext(next: string | null | undefined, fallback = "/app"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) {
    return fallback;
  }
  return next;
}

export function decide(pathname: string, search: string, state: AuthState): Decision {
  const now = state.now ?? Date.now();
  const isMfaRoute = pathname.startsWith("/mfa/");

  if (
    state.hasSession &&
    state.sessionStartedAt != null &&
    now - state.sessionStartedAt > SESSION_LIMIT_MS
  ) {
    return { type: "redirect", to: "/sign-in?reason=expired", signOut: true };
  }

  if (isPublicPath(pathname)) {
    // A signed-in aal1 user on an MFA page is exactly where they should be.
    return { type: "allow" };
  }

  if (!state.hasSession) {
    const next = encodeURIComponent(pathname + search);
    return { type: "redirect", to: `/sign-in?next=${next}` };
  }

  if (state.aal !== "aal2") {
    const next = encodeURIComponent(pathname + search);
    const target = state.nextLevel === "aal2" ? "/mfa/challenge" : "/mfa/enroll";
    return isMfaRoute ? { type: "allow" } : { type: "redirect", to: `${target}?next=${next}` };
  }

  return { type: "allow" };
}
