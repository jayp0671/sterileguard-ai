import { existsSync } from "node:fs";
import { type Browser, type Page, test } from "@playwright/test";
import { generateSync } from "otplib";
import { authFile, credentials, type Role } from "../roles";

/** Use a role's saved session, or skip the spec until demo users and E2E_* secrets exist. */
export function asRole(role: Role) {
  const file = authFile(role);
  test.skip(
    !existsSync(file),
    `no ${role} storage state: run sg demo seed-demo and set E2E_${role.toUpperCase()}_*`,
  );
  test.use({ storageState: existsSync(file) ? file : undefined });
}

/** A second signed-in context in the same test (for example a supervisor approving). */
export async function pageAs(browser: Browser, role: Role): Promise<Page> {
  const ctx = await browser.newContext({ storageState: authFile(role) });
  return ctx.newPage();
}

/** Fill the re-auth dialog with a fresh TOTP code for the role. */
export async function reauth(page: Page, role: Role) {
  const creds = credentials(role);
  if (!creds) throw new Error(`E2E_${role.toUpperCase()}_TOTP_SECRET is not set`);
  const dialog = page.getByRole("dialog", { name: "Confirm it's you" });
  await dialog.getByLabel(/code/i).fill(generateSync({ secret: creds.totpSecret }));
  await dialog.getByRole("button", { name: /verify|confirm/i }).click();
}

/** Accept the cookie banner with "Essential only" if it is showing. */
export async function essentialOnly(page: Page) {
  const button = page.getByRole("button", { name: "Essential only" });
  if (await button.isVisible().catch(() => false)) await button.click();
}

export const DEMO_DEPARTMENT = "00000000-0000-4000-8000-000000000003";
