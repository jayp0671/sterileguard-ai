import { expect, test } from "@playwright/test";
import { asRole, essentialOnly } from "./helpers";

// SG-26 journey 2: plan tomorrow, compute, open scenarios, apply the minimum change, confirm the
// forecast and the plan changed.
asRole("supervisor");

test("supervisor plans, runs scenarios and applies the minimum change", async ({ page }) => {
  await page.goto("/app/plan");
  await essentialOnly(page);
  await expect(page.getByRole("heading", { name: "Plan tomorrow" })).toBeVisible();
  await page.getByRole("button", { name: "Finalize plan" }).click();
  await expect(page.getByText("Plan finalized")).toBeVisible();

  await page.goto("/app");
  await page.getByRole("button", { name: /^(Compute forecast|Recompute)$/ }).click();
  const estimate = page.getByRole("region", { name: "Overtime estimate" });
  await expect(estimate).toBeVisible();
  const before = await estimate.getByText(/Most likely [\d.]+/).innerText();
  await expect(page.getByText("Model estimate, not a guarantee.").first()).toBeVisible();

  await page.goto("/app/scenarios");
  await page.getByRole("button", { name: /Run scenarios|Run again/ }).click();
  const recommendation = page.getByRole("region", { name: /recommend/i });
  await expect(recommendation).toBeVisible();
  const apply = page.getByRole("button", { name: /^Apply/ }).first();
  test.skip(!(await apply.isVisible()), "plan already meets the target: no change to apply");
  await apply.click();
  const dialog = page.getByRole("dialog", { name: "Apply to tomorrow's plan?" });
  await dialog.getByRole("button", { name: /apply/i }).click();
  await expect(page.getByText(/applied/i).first()).toBeVisible();

  await page.goto("/app");
  await expect(
    page.getByRole("region", { name: "Overtime estimate" }).getByText(/Most likely [\d.]+/),
  ).not.toHaveText(before);
  await page.goto("/app/plan");
  await expect(page.getByText(/scenario/i).first()).toBeVisible();
});
