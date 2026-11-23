import { expect, test } from "@playwright/test";
import { asRole, essentialOnly, pageAs } from "./helpers";

// SG-26 journey 3: technician logs a shift with the overtime helper and submits; a supervisor
// approves; the technician can no longer edit it.
asRole("technician");

test("technician logs, supervisor approves, the row locks", async ({ page, browser }) => {
  await page.goto("/app/log");
  await essentialOnly(page);
  await page.getByRole("button", { name: "Next" }).click(); // date step: yesterday by default
  await page.getByLabel("Overtime labor-hours past 3:00 PM").fill("3.5");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Submit for approval" }).click();
  await expect(page.getByText(/submitted/i).first()).toBeVisible();

  const sup = await pageAs(browser, "supervisor");
  await sup.goto("/app/history?status=submitted");
  const row = sup.getByRole("row").filter({ hasText: "3.5" }).first();
  await row.getByRole("checkbox").check();
  await sup
    .getByRole("button", { name: /approve/i })
    .first()
    .click();
  await sup
    .getByRole("dialog")
    .getByRole("button", { name: /approve/i })
    .click();
  await expect(sup.getByText(/approved/i).first()).toBeVisible();

  await page.goto("/app/history");
  const mine = page.getByRole("row").filter({ hasText: "3.5" }).first();
  await expect(mine.getByText("Approved")).toBeVisible();
  await mine.getByRole("button", { name: /Details for/ }).click();
  await expect(page.getByRole("button", { name: /^Edit/ })).toHaveCount(0);
});
