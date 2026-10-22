import { expect, test } from "@playwright/test";

test.describe("public pages", () => {
  test("home shows the product and the API status", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "SterileGuard AI" })).toBeVisible();
    await expect(page.getByTestId("api-health")).toBeVisible();
    await expect(page.getByText("Academic prototype. Not for clinical use.")).toBeVisible();
  });

  test("protected routes redirect to sign-in with next", async ({ page }) => {
    await page.goto("/app/settings");
    await expect(page).toHaveURL(/\/sign-in\?next=%2Fapp%2Fsettings/);
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });

  test("sign-in has no self-signup path", async ({ page }) => {
    await page.goto("/sign-in");
    await expect(page.getByText(/sign up|create account/i)).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Email me a sign-in link" })).toBeVisible();
  });
});
