import { expect, test } from "@playwright/test";
import { generateSync } from "otplib";

// SG-26 journey 1: invite -> accept -> password -> TOTP -> forecast page. Runs only against the
// local Supabase stack (the invite email is read from its mail catcher), never staging.
const MAILPIT = process.env.E2E_MAILPIT_URL ?? "http://127.0.0.1:54324";
test.skip(
  process.env.E2E_LOCAL_STACK !== "1",
  "needs the local Supabase stack (E2E_LOCAL_STACK=1)",
);

test("a new user is invited, sets a password, enrolls TOTP and lands on the forecast", async ({
  page,
  request,
}) => {
  const email = `e2e-onboard-${Date.now()}@example.test`;
  // The admin storage state comes from global setup against the local stack.
  await page.goto("/app/admin/users");
  await page.getByRole("button", { name: "Invite" }).click();
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Role").selectOption("technician");
  await page.getByRole("button", { name: "Send invite" }).click();
  await expect(page.getByText("Invite sent")).toBeVisible();

  // Mailpit (Supabase CLI 2.x) API; older CLIs used Inbucket at the same port.
  let link: string | undefined;
  await expect
    .poll(
      async () => {
        const res = await request.get(
          `${MAILPIT}/api/v1/search?query=to:${encodeURIComponent(email)}`,
        );
        const id = (await res.json()).messages?.[0]?.ID;
        if (!id) return null;
        const msg = await (await request.get(`${MAILPIT}/api/v1/message/${id}`)).json();
        link = /href="([^"]*accept-invite[^"]*)"/
          .exec(msg.HTML ?? "")?.[1]
          ?.replaceAll("&amp;", "&");
        return link ?? null;
      },
      { timeout: 30_000 },
    )
    .not.toBeNull();

  const fresh = await page.context().browser()?.newContext();
  const p = await fresh!.newPage();
  await p.goto(link!);
  await p.getByLabel("New password").fill("Corr3ct-Horse-Battery!");
  await p.getByLabel("Confirm password").fill("Corr3ct-Horse-Battery!");
  await p.getByRole("button", { name: /set password/i }).click();
  await p.waitForURL(/\/mfa\/enroll/);
  const secret = await p.getByTestId("totp-secret").innerText();
  await p.getByLabel("6-digit code").fill(generateSync({ secret: secret.replaceAll(" ", "") }));
  await p.getByRole("button", { name: "Verify" }).click();
  await p.waitForURL(/\/app$/);
  await expect(p.getByRole("heading", { name: /forecast/i })).toBeVisible();
});
