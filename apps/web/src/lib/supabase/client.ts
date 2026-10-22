import { createBrowserClient } from "@supabase/ssr";
import { env } from "@/lib/env";

/** Supabase client for client components. Sign-in and two-factor only; data goes via the API. */
export function createClient() {
  return createBrowserClient(env.supabaseUrl, env.supabaseKey);
}
