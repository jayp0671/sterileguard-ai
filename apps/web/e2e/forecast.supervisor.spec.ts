import { existsSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { authFile } from "./roles";

// SG-17: plan tomorrow, compute the forecast, read the drivers and the history table.
// Runs once demo users exist (SG-16) and the E2E_SUPERVISOR_* variables are set.
const file = authFile("supervisor");
test.skip(!existsSync(file), "no supervisor storage state; set E2E_SUPERVISOR_* env vars");
test.use({ storageState: existsSync(file) ? file : undefined });

test("supervisor plans tomorrow and computes the forecast", async ({ page }) => {
  await page.goto("/app/plan");
  await expect(page.getByRole("heading", { name: "Plan tomorrow" })).toBeVisible();
  await page.getByRole("button", { name: "Increase 7:00 AM staff" }).click();
  await page.getByRole("button", { name: "Finalize plan" }).click();
  await expect(page.getByText("Plan finalized")).toBeVisible();

  await page.goto("/app");
  const compute = page.getByRole("button", { name: /^(Compute forecast|Recompute)$/ });
  await compute.click();
  const estimate = page.getByRole("region", { name: "Overtime estimate" });
  await expect(estimate).toBeVisible();
  await expect(
    estimate.getByText(/Most likely [\d.]+, range [\d.]+ to [\d.]+ \(80%\)/),
  ).toBeVisible();
  await expect(estimate.getByText(/(Low|Moderate|High) burden/)).toBeVisible();
  await expect(page.getByText("Model estimate, not a guarantee.")).toBeVisible();

  const drivers = page
    .getByRole("region", { name: "What is driving tomorrow" })
    .getByRole("listitem");
  expect(await drivers.count()).toBeGreaterThanOrEqual(3);

  await page.getByRole("button", { name: "Why these factors?" }).click();
  await expect(page.getByRole("dialog")).toContainText("add up to the estimate exactly");
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "View as table" }).click();
  expect(await page.getByRole("table").getByRole("row").count()).toBeGreaterThan(1);
});
