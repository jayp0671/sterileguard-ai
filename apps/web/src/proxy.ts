import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";
import { decide, SESSION_STARTED_COOKIE } from "@/lib/auth/route-guard";
import { env } from "@/lib/env";

/**
 * Next.js 16 proxy (formerly middleware): refresh Supabase session cookies on every request,
 * then apply the route guard (no session -> sign-in; aal1 -> MFA; 12-hour absolute limit).
 */
export async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });
  const supabase = createServerClient(env.supabaseUrl, env.supabaseKey, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll(cookiesToSet) {
        for (const { name, value } of cookiesToSet) request.cookies.set(name, value);
        response = NextResponse.next({ request });
        for (const { name, value, options } of cookiesToSet) {
          response.cookies.set(name, value, options);
        }
      },
    },
  });

  // getUser() revalidates the token with Supabase Auth; never trust getSession() on the server.
  const {
    data: { user },
  } = await supabase.auth.getUser();
  let aal: "aal1" | "aal2" | null = null;
  let nextLevel: "aal1" | "aal2" | null = null;
  if (user) {
    const { data } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
    aal = (data?.currentLevel as "aal1" | "aal2" | null) ?? "aal1";
    nextLevel = (data?.nextLevel as "aal1" | "aal2" | null) ?? "aal1";
  }

  const started = Number(request.cookies.get(SESSION_STARTED_COOKIE)?.value ?? "");
  const decision = decide(request.nextUrl.pathname, request.nextUrl.search, {
    hasSession: Boolean(user),
    aal,
    nextLevel,
    sessionStartedAt: Number.isFinite(started) && started > 0 ? started : null,
  });

  if (decision.type === "allow") return response;

  if (decision.signOut) await supabase.auth.signOut({ scope: "local" });
  const redirect = NextResponse.redirect(new URL(decision.to, request.url));
  for (const cookie of response.cookies.getAll()) redirect.cookies.set(cookie);
  if (decision.signOut) redirect.cookies.delete(SESSION_STARTED_COOKIE);
  return redirect;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
