import { describe, expect, it } from "vitest";
import { navFor } from "@/lib/nav";

const hrefs = (roles: Parameters<typeof navFor>[0], showDevOnly = false) =>
  navFor(roles, { showDevOnly }).flatMap((s) => s.items.map((i) => i.href));

describe("navFor", () => {
  it("shows a technician only what they can use, with the read-only plan label", () => {
    const sections = navFor(["technician"]);
    const items = sections.flatMap((s) => s.items);
    expect(items.map((i) => i.href)).toEqual([
      "/app",
      "/app/plan",
      "/app/log",
      "/app/history",
      "/app/notifications",
      "/app/settings",
    ]);
    expect(items.find((i) => i.href === "/app/plan")?.label).toBe("Tomorrow's plan");
    expect(sections.map((s) => s.label)).not.toContain("Admin");
  });

  it("gives supervisors planning, scenarios and model performance", () => {
    const items = navFor(["supervisor"]).flatMap((s) => s.items);
    expect(items.find((i) => i.href === "/app/plan")?.label).toBe("Plan tomorrow");
    expect(items.map((i) => i.href)).toEqual(
      expect.arrayContaining(["/app/scenarios", "/app/model"]),
    );
    expect(items.map((i) => i.href)).not.toContain("/app/imports");
  });

  it("keeps the full label when a technician also has a writing role", () => {
    const items = navFor(["technician", "supervisor"]).flatMap((s) => s.items);
    expect(items.find((i) => i.href === "/app/plan")?.label).toBe("Plan tomorrow");
  });

  it("limits admin and platform sections to their roles", () => {
    expect(hrefs(["dept_admin"])).toContain("/app/admin/audit");
    expect(hrefs(["dept_admin"])).not.toContain("/app/platform/models");
    expect(hrefs(["platform_admin"])).toContain("/app/platform/models");
    expect(hrefs(["data_steward"])).toContain("/app/imports");
  });

  it("hides the style page unless dev-only items are allowed", () => {
    expect(hrefs(["technician"])).not.toContain("/app/style");
    expect(hrefs(["technician"], true)).toContain("/app/style");
  });
});
