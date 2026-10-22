import { existsSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { authFile } from "./roles";

// Example of a role-scoped spec. Runs once demo users exist (SG-16) and E2E_* env vars are set.
const file = authFile("supervisor");
test.skip(!existsSync(file), "no supervisor storage state; set E2E_SUPERVISOR_* env vars");
test.use({ storageState: existsSync(file) ? file : undefined });

test("signed-in supervisor sees settings with sign out of all devices", async ({ page }) => {
  await page.goto("/app/settings");
  await expect(page.getByRole("button", { name: "Sign out of all devices" })).toBeVisible();
});
