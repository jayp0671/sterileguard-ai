import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { API, server } from "@/test/msw";
import { postAuthEvent } from "./audit";

describe("postAuthEvent", () => {
  it("posts the event with the bearer token", async () => {
    let seen: { auth: string | null; body: unknown } | null = null;
    server.use(
      http.post(`${API}/v1/audit/auth-event`, async ({ request }) => {
        seen = { auth: request.headers.get("Authorization"), body: await request.json() };
        return HttpResponse.json({ status: "accepted" }, { status: 202 });
      }),
    );
    await postAuthEvent("sign_in_success", "tok");
    expect(seen).toEqual({ auth: "Bearer tok", body: { event: "sign_in_success" } });
  });

  it("never throws when the API is down", async () => {
    server.use(http.post(`${API}/v1/audit/auth-event`, () => HttpResponse.error()));
    await expect(postAuthEvent("sign_in_failure")).resolves.toBeUndefined();
  });
});
