import { expect, test } from "@playwright/test";
import { asRole, essentialOnly } from "./helpers";

// SG-26 journey 4: a data steward uploads a messy synthetic file, fixes one mapping and commits.
// The planted fake names, phone and email are reported as counts and never shown. The
// rejected-rows CSV downloads. All values are synthetic.
asRole("data_steward");

const PLANTED = ["Mario Hernandez", "Debra Jones", "248-555-0171", "stacie60@example.test"];
const csv = (stamp: number) =>
  [
    "Date,Employee,Patients,Morning staf,OT hrs,Clinic blocks,Notes",
    `2026-09-0${(stamp % 3) + 1},Mario Hernandez,332,3,6,4,call 248-555-0171 about the cart`,
    "2026-09-08,Debra Jones,268,2,4.75,3,washer slow",
    "2026-09-09,Debra Jones,9999,3,0,5,emailed stacie60@example.test",
  ].join("\n");

test("steward imports a messy file", async ({ page }) => {
  await page.goto("/app/imports");
  await essentialOnly(page);
  await page.getByLabel("Choose a file to import").setInputFiles({
    name: `e2e-week-${Date.now()}.csv`,
    mimeType: "text/csv",
    buffer: Buffer.from(csv(Date.now())),
  });
  await page.waitForURL(/\/app\/imports\?job=/);
  await expect(
    page.getByText(/1 column was removed because it looked like names or IDs/),
  ).toBeVisible();
  for (const s of PLANTED) await expect(page.getByText(s)).toHaveCount(0);

  await page.getByRole("combobox", { name: "Field for column Clinic blocks" }).click();
  await page.getByPlaceholder("Search fields").fill("clinic");
  await page.getByRole("option", { name: /Student clinic sessions/ }).click();
  await expect(
    page.getByRole("combobox", { name: "Field for column Clinic blocks" }),
  ).toContainText("Student clinic sessions");

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Rejected rows" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/^rejected-.*\.csv$/);

  await page.getByRole("button", { name: /^Commit \d+ valid rows$/ }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Commit rows" }).click();
  await expect(page.getByText(/rows committed/)).toBeVisible();
});
