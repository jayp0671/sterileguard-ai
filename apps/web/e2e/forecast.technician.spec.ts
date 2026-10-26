import { existsSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { authFile } from "./roles";

// SG-17: a technician reads the forecast and the plan but cannot recompute or edit.
const file = authFile("technician");
test.skip(!existsSync(file), "no technician storage state; set E2E_TECHNICIAN_* env vars");
test.use({ storageState: existsSync(file) ? file : undefined });

test("technician views the forecast without Recompute and the plan read only", async ({ page }) => {
  await page.goto("/app");
  await expect(page.getByRole("heading", { name: /^Tomorrow, / })).toBeVisible();
  await expect(page.getByRole("button", { name: "Recompute" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Compute forecast" })).toHaveCount(0);

  await page.getByRole("link", { name: "View plan" }).click();
  await expect(page.getByRole("heading", { name: "Tomorrow's plan" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Finalize plan" })).toHaveCount(0);
});
