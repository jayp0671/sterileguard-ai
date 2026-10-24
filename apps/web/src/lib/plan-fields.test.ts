import spec from "@sg/contracts/openapi.json";
import { describe, expect, it } from "vitest";
import { fieldErrors, GROUPS, nextWorkday, planFields, planSchema } from "@/lib/plan-fields";

type Prop = {
  anyOf?: { minimum?: number; maximum?: number; type?: string }[];
  minimum?: number;
  maximum?: number;
};
const props =
  (
    spec as unknown as {
      components: { schemas: Record<string, { properties: Record<string, Prop> }> };
    }
  ).components.schemas.PlanPut?.properties ?? {};

const valid = { regular_patients: 350, morning_staff_present: 3, ot_available_staff: 2 };

describe("plan fields from openapi.json", () => {
  const fields = planFields();

  it("covers every plan input with a label and a known section", () => {
    expect(fields.map((f) => f.name).sort()).toEqual(
      Object.keys(props)
        .filter((k) => !["status", "backfill"].includes(k))
        .sort(),
    );
    const groups = new Set(GROUPS.map((g) => g.key));
    for (const f of fields) {
      expect(f.label).not.toBe(f.name);
      expect(groups.has(f.group)).toBe(true);
    }
  });

  it("uses exactly the API's ranges", () => {
    for (const f of fields.filter((x) => x.kind === "int")) {
      const p = props[f.name];
      const branch = p?.anyOf?.find((b) => b.type !== "null") ?? p;
      expect([f.min, f.max]).toEqual([branch?.minimum, branch?.maximum]);
    }
  });

  it("rejects out-of-range values with field-specific messages", () => {
    const errs = fieldErrors({ ...valid, regular_patients: 801, mf_cases: -1 });
    expect(errs.regular_patients).toMatch(/at most 800/);
    expect(errs.mf_cases).toMatch(/at least 0/);
    expect(fieldErrors(valid)).toEqual({});
  });

  it("requires Tier 1 inputs and enforces the overtime cross-check", () => {
    expect(planSchema().safeParse({ morning_staff_present: 3 }).success).toBe(false);
    expect(fieldErrors({ ...valid, ot_available_staff: 4 }).ot_available_staff).toMatch(
      /cannot exceed/,
    );
  });
});

describe("nextWorkday", () => {
  it("skips weekends in the department time zone", () => {
    expect(nextWorkday(new Date("2026-10-23T16:00:00Z"))).toBe("2026-10-26"); // Friday -> Monday
    expect(nextWorkday(new Date("2026-10-20T16:00:00Z"))).toBe("2026-10-21");
    // 01:00 UTC Wednesday is still Tuesday evening in New York
    expect(nextWorkday(new Date("2026-10-21T01:00:00Z"))).toBe("2026-10-21");
  });
});
