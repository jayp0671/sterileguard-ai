import { mkdirSync } from "node:fs";
import path from "node:path";
import { chromium, type FullConfig } from "@playwright/test";
import { generateSync } from "otplib";
import { authFile, credentials, ROLES } from "./roles";

/**
 * Sign in once per role (password, then TOTP) and save storage state to e2e/.auth/<role>.json.
 * Roles without E2E_* credentials are skipped, so public-page specs still run before demo users
 * exist (SG-16). Specs that need a role use `test.use({ storageState: authFile(role) })` and
 * skip themselves when the file is missing.
 */
export default async function globalSetup(config: FullConfig) {
  mkdirSync(path.join(__dirname, ".auth"), { recursive: true });
  const baseURL = config.projects[0]?.use.baseURL ?? "http://localhost:3000";
  const configured = ROLES.filter((r) => credentials(r));
  if (configured.length === 0) return;

  const browser = await chromium.launch();
  for (const role of configured) {
    const creds = credentials(role);
    if (!creds) continue;
    const page = await browser.newPage({ baseURL });
    await page.goto("/sign-in");
    await page.getByLabel("Email").fill(creds.email);
    await page.getByLabel("Password").fill(creds.password);
    // Turnstile's test site key passes automatically; wait for it before submitting.
    await page.waitForTimeout(1500);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL(/\/mfa\/challenge/);
    await page.getByLabel("6-digit code").fill(generateSync({ secret: creds.totpSecret }));
    await page.getByRole("button", { name: "Verify" }).click();
    await page.waitForURL(/\/app/);
    await page.context().storageState({ path: authFile(role) });
    await page.close();
  }
  await browser.close();
}
