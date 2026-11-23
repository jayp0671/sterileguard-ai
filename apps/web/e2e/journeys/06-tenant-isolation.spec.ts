import { expect, test } from "@playwright/test";
import { asRole, DEMO_DEPARTMENT, essentialOnly } from "./helpers";

// SG-26 journey 6: a technician of another department points the app at department A by ID and
// gets not-found or empty states everywhere (the API answers 404 for non-members).
asRole("outsider");

const PAGES = [
  "/app",
  "/app/plan",
  "/app/history",
  "/app/scenarios",
  "/app/imports",
  "/app/model",
  "/app/admin/audit",
];

test("an outsider sees nothing of department A", async ({ page }) => {
  const forbidden: string[] = [];
  page.on("response", (r) => {
    if (r.url().includes(`department_id=${DEMO_DEPARTMENT}`) && r.status() === 200)
      forbidden.push(r.url());
  });
  await page.goto("/app");
  await essentialOnly(page);
  await page.evaluate((id) => window.localStorage.setItem("sg.department", id), DEMO_DEPARTMENT);
  for (const path of PAGES) {
    await page.goto(path);
    await page.waitForLoadState("load");
    await page.waitForTimeout(1500);
    await expect(
      page.getByText(/Overtime estimate|Commit \d+ valid rows|Users and invites/),
    ).toHaveCount(0);
  }
  expect(forbidden, "no department A data may come back").toEqual([]);
});
