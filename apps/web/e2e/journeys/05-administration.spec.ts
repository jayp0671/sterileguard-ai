import { expect, test } from "@playwright/test";
import { credentials } from "../roles";
import { asRole, essentialOnly, reauth } from "./helpers";

// SG-26 journey 5: a dept admin changes a role (re-auth with TOTP), then finds the change in
// the audit log with before and after. The role is changed back at the end.
asRole("dept_admin");

test("admin changes a role and sees it in the audit log", async ({ page }) => {
  const tech = credentials("technician");
  test.skip(!tech, "needs E2E_TECHNICIAN_EMAIL to find the demo technician");
  await page.goto("/app/admin/users");
  await essentialOnly(page);
  const row = page.getByRole("row").filter({ hasText: tech!.email });

  async function setRole(label: string) {
    await row.getByRole("button", { name: "Change role" }).click();
    const dialog = page.getByRole("dialog", { name: "Change role" });
    for (const box of await dialog.getByRole("checkbox").all()) await box.uncheck();
    await dialog.getByLabel(label).check();
    await dialog.getByRole("button", { name: "Continue" }).click();
    await reauth(page, "dept_admin");
    await expect(page.getByText("Roles updated")).toBeVisible();
  }

  await setRole("Supervisor");
  await expect(row).toContainText("Supervisor");

  await page.goto("/app/admin/audit");
  await page.getByLabel("What").selectOption("memberships");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await page.getByRole("row").nth(1).getByRole("button").click();
  const drawer = page.getByRole("dialog");
  await expect(drawer).toContainText("memberships");
  await expect(drawer.getByText(/"(supervisor|technician)"/).first()).toBeVisible();

  await page.goto("/app/admin/users");
  await setRole("Technician");
});
