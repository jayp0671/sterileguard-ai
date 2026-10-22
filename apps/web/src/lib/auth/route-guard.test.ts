import { describe, expect, it } from "vitest";
import { decide, isPublicPath, SESSION_LIMIT_MS, safeNext } from "./route-guard";

const signedOut = { hasSession: false, aal: null, nextLevel: null } as const;
const aal1NoFactor = { hasSession: true, aal: "aal1", nextLevel: "aal1" } as const;
const aal1WithFactor = { hasSession: true, aal: "aal1", nextLevel: "aal2" } as const;
const aal2 = { hasSession: true, aal: "aal2", nextLevel: "aal2" } as const;

describe("decide", () => {
  it("sends signed-out users to sign-in with next", () => {
    expect(decide("/app", "?d=1", signedOut)).toEqual({
      type: "redirect",
      to: "/sign-in?next=%2Fapp%3Fd%3D1",
    });
  });

  it("sends aal1 users without a factor to enroll", () => {
    const d = decide("/app/plan", "", aal1NoFactor);
    expect(d).toMatchObject({ type: "redirect" });
    expect(d.type === "redirect" && d.to.startsWith("/mfa/enroll?next=")).toBe(true);
  });

  it("sends aal1 users with a factor to challenge", () => {
    const d = decide("/app", "", aal1WithFactor);
    expect(d.type === "redirect" && d.to.startsWith("/mfa/challenge")).toBe(true);
  });

  it("allows aal2 users into the app", () => {
    expect(decide("/app/settings", "", aal2)).toEqual({ type: "allow" });
  });

  it.each([
    "/",
    "/sign-in",
    "/magic-link",
    "/accept-invite",
    "/reset-password",
    "/mfa/enroll",
    "/trust/privacy",
    "/status",
    "/auth/confirm",
  ])("allows public route %s when signed out", (path) => {
    expect(decide(path, "", signedOut)).toEqual({ type: "allow" });
  });

  it("signs out sessions older than 12 hours, even on public pages", () => {
    const now = 1_000_000_000_000;
    const d = decide("/app", "", { ...aal2, sessionStartedAt: now - SESSION_LIMIT_MS - 1, now });
    expect(d).toEqual({ type: "redirect", to: "/sign-in?reason=expired", signOut: true });
    const ok = decide("/app", "", {
      ...aal2,
      sessionStartedAt: now - SESSION_LIMIT_MS + 1000,
      now,
    });
    expect(ok).toEqual({ type: "allow" });
  });
});

describe("isPublicPath", () => {
  it("does not treat lookalike paths as public", () => {
    expect(isPublicPath("/app")).toBe(false);
    expect(isPublicPath("/sign-in-evil")).toBe(false);
    expect(isPublicPath("/trust/privacy")).toBe(true);
    expect(isPublicPath("/mfa")).toBe(true);
  });
});

describe("safeNext", () => {
  it.each([
    ["/app/plan", "/app/plan"],
    ["//evil.example", "/app"],
    ["https://evil.example", "/app"],
    ["/\\evil", "/app"],
    [null, "/app"],
  ])("safeNext(%s) = %s", (input, expected) => {
    expect(safeNext(input)).toBe(expected);
  });
});
