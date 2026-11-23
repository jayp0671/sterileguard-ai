import { existsSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { authFile } from "../roles";

// SG-26 journey 7: cookie banner without analytics, idle timeout, language switch.
const POSTHOG = /posthog\.com|i\.posthog/;

test("Essential only makes zero requests to the PostHog host", async ({ page }) => {
  const hits: string[] = [];
  page.on("request", (r) => {
    if (POSTHOG.test(r.url())) hits.push(r.url());
  });
  await page.goto("/trust");
  const banner = page.getByRole("region", { name: "Cookie choices" });
  await expect(banner).toBeVisible();
  await banner.getByRole("button", { name: "Essential only" }).click();
  await expect(banner).toHaveCount(0);
  await page.goto("/trust/privacy");
  await page.goto("/sign-in");
  await page.waitForLoadState("load");
  await page.waitForTimeout(2000); // let late scripts fire (dev HMR and Turnstile never go idle)
  expect(hits).toEqual([]);
  const consent = (await page.context().cookies()).find((c) => c.name === "sg_consent");
  expect(JSON.parse(decodeURIComponent(consent?.value ?? "{}")).analytics).toBe(false);
});

test("footer notice and legal links are on public pages", async ({ page }) => {
  await page.goto("/trust/hipaa-notice");
  await expect(
    page.getByText("Academic prototype. Not for clinical use. Do not enter patient information."),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "HIPAA Notice" })).toBeVisible();
  await expect(
    page.getByText("Template for an academic prototype. Not legal advice."),
  ).toBeVisible();
  const txt = await page.request.get("/.well-known/security.txt");
  expect(await txt.text()).toMatch(/^Contact: /m);
});

test.describe("idle timeout", () => {
  const file = authFile("technician");
  test.skip(!existsSync(file), "no technician storage state");
  test.use({ storageState: existsSync(file) ? file : undefined });

  test("warns at 14 minutes and signs out at 15", async ({ page }) => {
    await page.clock.install();
    await page.goto("/app");
    await page.clock.fastForward("14:01");
    await expect(page.getByRole("dialog", { name: "Still there?" })).toBeVisible();
    await page.clock.fastForward("01:00");
    await page.waitForURL(/\/sign-in/);
  });
});

// TODO(SG-27): switching to Spanish updates the UI. Enable when es messages and locale routing land.
test.fixme("switching to Spanish updates the UI", async () => {});
