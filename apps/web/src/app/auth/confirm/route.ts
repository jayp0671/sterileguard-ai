import type { EmailOtpType } from "@supabase/supabase-js";
import { type NextRequest, NextResponse } from "next/server";
import { safeNext } from "@/lib/auth/route-guard";
import { createClient } from "@/lib/supabase/server";

const DEFAULT_NEXT: Record<string, string> = {
  invite: "/accept-invite",
  recovery: "/reset-password?step=confirm",
  email: "/mfa/challenge",
  magiclink: "/mfa/challenge",
};

/**
 * Email links (invite, magic link, password reset) land here with a token_hash. The email
 * templates in ops/runbooks/auth-settings.md point to:
 *   {{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=<invite|email|recovery>
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const tokenHash = searchParams.get("token_hash");
  const type = searchParams.get("type") as EmailOtpType | null;
  const next = safeNext(searchParams.get("next"), DEFAULT_NEXT[type ?? ""] ?? "/app");

  if (tokenHash && type) {
    const supabase = await createClient();
    const { error } = await supabase.auth.verifyOtp({ type, token_hash: tokenHash });
    if (!error) {
      const response = NextResponse.redirect(new URL(next, request.url));
      response.cookies.set("sg_session_started_at", String(Date.now()), {
        path: "/",
        sameSite: "lax",
        secure: request.nextUrl.protocol === "https:",
      });
      return response;
    }
  }
  return NextResponse.redirect(new URL("/sign-in?reason=link", request.url));
}
