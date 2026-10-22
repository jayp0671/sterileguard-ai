"use client";

import { SESSION_STARTED_COOKIE } from "@/lib/auth/route-guard";
import { createClient } from "@/lib/supabase/client";
import { postAuthEvent } from "./audit";

/** Record sign-in time for the 12-hour absolute limit (checked by the proxy on every request). */
export function markSessionStarted(now = Date.now()) {
  const secure = window.location.protocol === "https:" ? "; secure" : "";
  document.cookie = `${SESSION_STARTED_COOKIE}=${now}; path=/; samesite=lax${secure}`;
}

export function clearSessionStarted() {
  document.cookie = `${SESSION_STARTED_COOKIE}=; path=/; max-age=0`;
}

/** After reaching aal2: convert pending invites into memberships (SG-04 accept flow). */
export async function onAal2Reached() {
  const supabase = createClient();
  await supabase.rpc("accept_pending_invites");
  const { data } = await supabase.auth.getSession();
  await postAuthEvent("sign_in_success", data.session?.access_token);
}

export async function signOut(
  reason: "idle" | "expired" | "user",
  scope: "local" | "global" = "local",
) {
  const supabase = createClient();
  const { data } = await supabase.auth.getSession();
  const event =
    scope === "global"
      ? "sign_out_global"
      : reason === "idle"
        ? "idle_timeout"
        : reason === "expired"
          ? "session_expired"
          : "sign_out";
  await postAuthEvent(event, data.session?.access_token);
  await supabase.auth.signOut({ scope });
  clearSessionStarted();
  window.location.assign(reason === "user" ? "/sign-in" : `/sign-in?reason=${reason}`);
}
