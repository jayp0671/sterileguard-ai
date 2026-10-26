import path from "node:path";
import { defineConfig, devices } from "@playwright/test";
import { config as loadEnv } from "dotenv";

loadEnv({ path: path.resolve(__dirname, "../../.env"), quiet: true });

const baseURL = process.env.E2E_BASE_URL || "http://localhost:3000";
const isCI = Boolean(process.env.CI);
const reportDir = path.resolve(__dirname, "../../ops/reports/test");

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  reporter: [
    ["list"],
    ["junit", { outputFile: path.join(reportDir, "junit-e2e.xml") }],
    ["html", { open: "never", outputFolder: "playwright-report" }],
  ],
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL,
    // Vercel preview protection: the bypass secret lets CI reach a protected preview.
    extraHTTPHeaders: process.env.VERCEL_AUTOMATION_BYPASS_SECRET
      ? { "x-vercel-protection-bypass": process.env.VERCEL_AUTOMATION_BYPASS_SECRET }
      : undefined,
    trace: "on-first-retry",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
    { name: "tablet", use: { ...devices["iPad (gen 7)"], hasTouch: true } },
  ],
  // Locally, start the whole stack unless E2E_BASE_URL points somewhere else.
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: "uv run sg dev --no-db",
        cwd: path.resolve(__dirname, "../.."),
        url: baseURL,
        reuseExistingServer: !isCI,
        timeout: 180_000,
        stdout: "ignore",
      },
});
