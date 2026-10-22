import { describe, expect, it } from "vitest";
import { checkPassword } from "./password";

describe("checkPassword", () => {
  it("rejects passwords under 12 characters", () => {
    const r = checkPassword("Tr0ub4dor&3");
    expect(r.tooShort).toBe(true);
    expect(r.ok).toBe(false);
  });

  it("rejects long but common passwords", () => {
    expect(checkPassword("password1234").ok).toBe(false);
    expect(checkPassword("sterileguard2026").ok).toBe(false);
  });

  it("accepts a long random passphrase", () => {
    const r = checkPassword("violet-kettle-orbit-91-canyon");
    expect(r.ok).toBe(true);
    expect(r.score).toBeGreaterThanOrEqual(3);
  });
});
