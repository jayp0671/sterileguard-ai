import { expect, test } from "@playwright/test";

// SG-16: `sg release smoke --env staging`. The web sign-in page loads, the API is alive, and it
// is ready with a model version loaded. SMOKE_API_URL comes from the sg command.
const api = process.env.SMOKE_API_URL;

test("sign-in page loads", async ({ page }) => {
  await page.goto("/sign-in");
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});

test("API is healthy and ready with a model", async ({ request }) => {
  test.skip(!api, "SMOKE_API_URL not set");
  const health = await request.get(`${api}/health`);
  expect(health.ok()).toBeTruthy();
  expect((await health.json()).status).toBe("ok");
  const ready = await request.get(`${api}/ready`);
  expect(ready.ok()).toBeTruthy();
  const body = await ready.json();
  expect(body.status).toBe("ready");
  expect(body.models.full).toMatch(/^\d{8}-\d{4}-[0-9a-f]+$/);
});
