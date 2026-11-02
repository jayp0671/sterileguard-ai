import { beforeEach, describe, expect, it } from "vitest";
import {
  clearDraft,
  draftBody,
  draftOvertime,
  emptyDraft,
  hoursPast,
  loadDraft,
  overtimeTotal,
  saveDraft,
} from "@/lib/shift-log";

const DEPT = "dept-1";

describe("overtime helper", () => {
  it("adds hours past 3 PM from end times only", () => {
    expect(overtimeTotal(["20:00", "19:30", "18:00"])).toBe(12.5);
    expect(hoursPast("15:00")).toBe(0);
    expect(hoursPast("14:30")).toBe(0);
    expect(hoursPast("16:20")).toBeCloseTo(1.333, 3);
    expect(overtimeTotal(["16:20", "16:20", "16:20"])).toBe(4);
  });

  it("ignores rows that are not times", () => {
    expect(overtimeTotal(["20:00", "", "25:00", "7pm"])).toBe(5);
    expect(hoursPast("nope")).toBeNull();
  });

  it("stores only the total, never the end times", () => {
    const d = {
      ...emptyDraft("2026-11-02"),
      otMode: "helper" as const,
      endTimes: ["20:00", "19:30"],
    };
    expect(draftOvertime(d)).toBe(9.5);
    const body = draftBody(d);
    expect(body.ot_labor_hours).toBe(9.5);
    expect(JSON.stringify(body)).not.toContain("19:30");
    expect(Object.keys(body)).not.toContain("endTimes");
  });

  it("validates a typed total", () => {
    expect(draftOvertime({ ...emptyDraft("d"), otTotal: "7.25" })).toBe(7.25);
    expect(draftOvertime({ ...emptyDraft("d"), otTotal: "-1" })).toBeNull();
    expect(draftOvertime({ ...emptyDraft("d"), otTotal: "" })).toBeNull();
  });
});

describe("draft recovery", () => {
  beforeEach(() => window.localStorage.clear());

  it("restores an unsent draft from localStorage", () => {
    const draft = { ...emptyDraft("2026-11-02"), otTotal: "6", notes: "washer 2 down", step: 2 };
    saveDraft(DEPT, draft);
    expect(loadDraft(DEPT)).toEqual(draft);
    clearDraft(DEPT);
    expect(loadDraft(DEPT)).toBeNull();
  });

  it("survives broken or missing storage", () => {
    window.localStorage.setItem(`sg.shift-draft.${DEPT}`, "{not json");
    expect(loadDraft(DEPT)).toBeNull();
    const broken = {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("quota");
      },
      removeItem: () => {
        throw new Error("denied");
      },
    } as unknown as Storage;
    expect(loadDraft(DEPT, broken)).toBeNull();
    expect(() => saveDraft(DEPT, emptyDraft("d"), broken)).not.toThrow();
    expect(() => clearDraft(DEPT, broken)).not.toThrow();
  });
});
