import { describe, expect, it } from "vitest";
import type { OptionOut, ScenarioOut } from "@/hooks/use-scenarios";
import { bounds, changeLines, changeSummary, likelyClass, normalize } from "@/lib/scenarios";

const values = {
  morning_staff_present: 3,
  aft_11_staff: 2,
  aft_13_staff: 1,
  outside_support_staff: 1,
  ot_available_staff: 3,
};
const opt = (v: Partial<typeof values>, changes: Partial<typeof values> = {}): OptionOut =>
  ({ values: { ...values, ...v }, changes: { ...changes } }) as unknown as OptionOut;
const scenario = {
  bounds: {
    morning_staff_present: [2, 5],
    aft_11_staff: [2, 4],
    aft_13_staff: [1, 3],
    outside_support_staff: [1, 3],
    ot_available_staff: [0, 3],
  },
} as unknown as ScenarioOut;

describe("scenario helpers", () => {
  it("never lets volunteers exceed the morning staff count", () => {
    expect(bounds(scenario, "ot_available_staff", { ...values, morning_staff_present: 2 })).toEqual(
      [0, 2],
    );
    expect(normalize(scenario, { ...values, morning_staff_present: 2 }).ot_available_staff).toBe(2);
  });

  it("lists exact changes against the plan", () => {
    const base = opt({});
    expect(changeLines(opt({ aft_11_staff: 3, outside_support_staff: 2 }), base)).toEqual([
      "11:00 AM start: 2 to 3",
      "Outside support: 1 to 2",
    ]);
    expect(changeSummary(opt({}, { aft_11_staff: 1, ot_available_staff: -1 }))).toBe(
      "+1 at 11:00, 3 willing to stay",
    );
    expect(changeSummary(opt({}))).toBe("Plan as it is");
  });

  it("picks the most likely burden class", () => {
    expect(likelyClass({ low: 0.2, moderate: 0.5, high: 0.3 })).toBe("moderate");
  });
});
