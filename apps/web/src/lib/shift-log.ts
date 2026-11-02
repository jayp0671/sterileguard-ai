/**
 * Log a shift (SG-20): the "Who stayed past 3 PM?" helper and draft recovery.
 *
 * The helper takes end times only (no names field exists) and adds up the hours worked past
 * the scheduled 3:00 PM end. Only the total is stored.
 */

export const SCHEDULED_END = "15:00";

/** "19:30" -> minutes after midnight, or null when it is not a valid HH:MM time. */
export function minutes(hhmm: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(hhmm.trim());
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  if (h > 23 || min > 59) return null;
  return h * 60 + min;
}

/** Hours past 3:00 PM for one end time (0 when they left on time or earlier). */
export function hoursPast(end: string, scheduledEnd = SCHEDULED_END): number | null {
  const e = minutes(end);
  const s = minutes(scheduledEnd) ?? 900;
  if (e === null) return null;
  return Math.max(0, e - s) / 60;
}

/** Total overtime hours from end times: 20:00, 19:30, 18:00 -> 5 + 4.5 + 3 = 12.5. Invalid
 * rows are ignored; the result is rounded to 2 decimals like the database column. */
export function overtimeTotal(ends: string[], scheduledEnd = SCHEDULED_END): number {
  const total = ends
    .map((e) => hoursPast(e, scheduledEnd))
    .reduce<number>((sum, h) => sum + (h ?? 0), 0);
  return Math.round(total * 100) / 100;
}

export type ShiftDraft = {
  shiftDate: string;
  otMode: "total" | "helper";
  otTotal: string;
  endTimes: string[];
  emergency: string;
  returnedUnused: string;
  downtime: string;
  notes: string;
  backfill: boolean;
  plan: Record<string, string>;
  serverId: string | null;
  step: number;
  savedAt: string;
};

export const emptyDraft = (shiftDate: string): ShiftDraft => ({
  shiftDate,
  otMode: "total",
  otTotal: "",
  endTimes: [""],
  emergency: "",
  returnedUnused: "",
  downtime: "",
  notes: "",
  backfill: false,
  plan: {},
  serverId: null,
  step: 0,
  savedAt: "",
});

export const draftKey = (departmentId: string) => `sg.shift-draft.${departmentId}`;

/** The draft saved in this browser, if any. Storage can be missing or full: never throws. */
export function loadDraft(departmentId: string, storage?: Storage): ShiftDraft | null {
  try {
    const raw = (storage ?? window.localStorage).getItem(draftKey(departmentId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ShiftDraft>;
    if (typeof parsed.shiftDate !== "string") return null;
    return { ...emptyDraft(parsed.shiftDate), ...parsed };
  } catch {
    return null;
  }
}

export function saveDraft(departmentId: string, draft: ShiftDraft, storage?: Storage): void {
  try {
    (storage ?? window.localStorage).setItem(draftKey(departmentId), JSON.stringify(draft));
  } catch {
    // Private mode or a full quota: the server draft still holds the work.
  }
}

export function clearDraft(departmentId: string, storage?: Storage): void {
  try {
    (storage ?? window.localStorage).removeItem(draftKey(departmentId));
  } catch {
    // nothing to clear
  }
}

/** The overtime total the draft will store, or null while it is not a valid number. */
export function draftOvertime(d: ShiftDraft): number | null {
  if (d.otMode === "helper") {
    const valid = d.endTimes.filter((e) => e.trim() !== "");
    if (valid.length === 0 || valid.some((e) => minutes(e) === null)) return null;
    return overtimeTotal(valid);
  }
  if (d.otTotal.trim() === "") return null;
  const n = Number(d.otTotal);
  return Number.isFinite(n) && n >= 0 && n <= 60 ? n : null;
}

const int = (s: string) => (s.trim() === "" ? null : Number.parseInt(s, 10));

/** The API body for a draft (only the total overtime; never the end times). */
export function draftBody(d: ShiftDraft) {
  return {
    ot_labor_hours: draftOvertime(d) ?? 0,
    emergency_intake_patients: int(d.emergency),
    returned_unused_estimate: int(d.returnedUnused),
    equipment_downtime_minutes: int(d.downtime),
    notes: d.notes.trim() === "" ? null : d.notes.trim(),
  };
}
