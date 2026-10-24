import { z } from "zod";

/** Public runtime config. Validated at build time (next.config.ts) and at first import. */
const schema = z
  .object({
    NEXT_PUBLIC_SUPABASE_URL: z.url(),
    // Supabase now issues publishable keys (sb_publishable_...); legacy projects use the anon key.
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: z.string().min(1).optional(),
    NEXT_PUBLIC_SUPABASE_ANON_KEY: z.string().min(1).optional(),
    NEXT_PUBLIC_API_URL: z.url(),
    NEXT_PUBLIC_SITE_URL: z.url().default("http://localhost:3000"),
    // development | staging | production. Dev-only pages (the /app/style page) need non-production.
    NEXT_PUBLIC_APP_ENV: z.enum(["development", "staging", "production"]).default("development"),
  })
  .refine((v) => v.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? v.NEXT_PUBLIC_SUPABASE_ANON_KEY, {
    message: "Set NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY or NEXT_PUBLIC_SUPABASE_ANON_KEY",
    path: ["NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"],
  })
  .transform((v) => ({
    supabaseUrl: v.NEXT_PUBLIC_SUPABASE_URL,
    supabaseKey: (v.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ??
      v.NEXT_PUBLIC_SUPABASE_ANON_KEY) as string,
    apiUrl: v.NEXT_PUBLIC_API_URL.replace(/\/$/, ""),
    siteUrl: v.NEXT_PUBLIC_SITE_URL.replace(/\/$/, ""),
    appEnv: v.NEXT_PUBLIC_APP_ENV,
  }));

export type Env = z.infer<typeof schema>;

export function parseEnv(source: Record<string, string | undefined>): Env {
  const cleaned = Object.fromEntries(
    Object.entries(source).map(([k, v]) => [k, v === "" ? undefined : v]),
  );
  const result = schema.safeParse(cleaned);
  if (!result.success) {
    const lines = result.error.issues.map((i) => `  - ${i.path.join(".")}: ${i.message}`);
    throw new Error(
      `Invalid web environment. Fix these in .env or the Vercel project:\n${lines.join("\n")}`,
    );
  }
  return result.data;
}
