import { describe, expect, it } from "vitest";
import { parseEnv } from "./env-schema";

const valid = {
  NEXT_PUBLIC_SUPABASE_URL: "http://127.0.0.1:54321",
  NEXT_PUBLIC_SUPABASE_ANON_KEY: "anon",
  NEXT_PUBLIC_API_URL: "http://localhost:8000/",
};

describe("parseEnv", () => {
  it("parses a valid environment and trims trailing slashes", () => {
    const env = parseEnv(valid);
    expect(env.apiUrl).toBe("http://localhost:8000");
    expect(env.supabaseKey).toBe("anon");
    expect(env.siteUrl).toBe("http://localhost:3000");
  });

  it("prefers the publishable key", () => {
    const env = parseEnv({ ...valid, NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_x" });
    expect(env.supabaseKey).toBe("sb_publishable_x");
  });

  it.each(["NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_API_URL"])(
    "throws a clear message when %s is missing",
    (name) => {
      expect(() => parseEnv({ ...valid, [name]: undefined })).toThrow(name);
    },
  );

  it("throws when no Supabase key is set (empty strings count as missing)", () => {
    expect(() => parseEnv({ ...valid, NEXT_PUBLIC_SUPABASE_ANON_KEY: "" })).toThrow(
      /PUBLISHABLE_KEY or NEXT_PUBLIC_SUPABASE_ANON_KEY/,
    );
  });
});
