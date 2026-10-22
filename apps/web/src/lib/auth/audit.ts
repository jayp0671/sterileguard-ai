import type { components } from "@sg/contracts";
import { api } from "@/lib/api";

export type AuthEventName = components["schemas"]["AuthEvent"]["event"];

/** Best-effort audit of auth events (plan §9.2). Never blocks or breaks the auth flow. */
export async function postAuthEvent(event: AuthEventName, accessToken?: string | null) {
  try {
    await api(() => accessToken).POST("/v1/audit/auth-event", { body: { event } });
  } catch {
    // The API may be asleep (free tier). Supabase's own auth logs still record the event.
  }
}
