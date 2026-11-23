// Public-page screenshots for PR descriptions (SG-25). Usage:
//   node e2e/screenshots.mjs https://sterileguard-ai.vercel.app ../../docs/screenshots/sprint-5
import { mkdirSync } from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

const [base = "http://localhost:3000", out = "../../docs/screenshots/sprint-5"] = process.argv.slice(2);
const PAGES = [
  ["trust-center", "/trust"],
  ["trust-hipaa-notice", "/trust/hipaa-notice"],
  ["trust-cookies", "/trust/cookies"],
];
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
for (const [name, url] of PAGES) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(new URL(url, base).toString(), { waitUntil: "load" });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(out, `${name}.png`), fullPage: false });
  if (name === "trust-center") {
    await page.getByRole("button", { name: "Preferences" }).click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(out, "cookie-preferences.png") });
  }
  await page.close();
}
await browser.close();
console.log(`wrote ${PAGES.length + 1} screenshots to ${out}`);
