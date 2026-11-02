import type { OptionOut, ScenarioOut } from "@/hooks/use-scenarios";

/** Levers in display order, with the start time each one stands for. */
export const LEVERS = [
  { key: "morning_staff_present", label: "7:00 AM staff", short: "7:00" },
  { key: "aft_11_staff", label: "11:00 AM start", short: "11:00" },
  { key: "aft_13_staff", label: "1:00 PM start", short: "13:00" },
  { key: "outside_support_staff", label: "Outside support", short: "Outside" },
  { key: "ot_available_staff", label: "Staff willing to stay", short: "Stay" },
] as const;

export type LeverKey = (typeof LEVERS)[number]["key"];
export type LeverValues = Record<LeverKey, number>;

export const VOLUNTEERS: LeverKey = "ot_available_staff";
export const DEBOUNCE_MS = 400;

export function leverValues(option: OptionOut): LeverValues {
  return Object.fromEntries(LEVERS.map((l) => [l.key, option.values[l.key] ?? 0])) as LeverValues;
}

/** The grid option for a set of lever values (every stepper position is in the grid). */
export function findOption(scenario: ScenarioOut, values: LeverValues): OptionOut | undefined {
  return scenario.options.find((o) => LEVERS.every((l) => o.values[l.key] === values[l.key]));
}

/** Bounds per lever; volunteers can never exceed the morning staff count. */
export function bounds(
  scenario: ScenarioOut,
  key: LeverKey,
  values: LeverValues,
): [number, number] {
  const [lo, hi] = scenario.bounds[key] ?? [0, 0];
  if (key === VOLUNTEERS) return [lo ?? 0, Math.min(hi ?? 0, values.morning_staff_present)];
  return [lo ?? 0, hi ?? 0];
}

/** Clamp volunteers after the morning count changes. */
export function normalize(scenario: ScenarioOut, values: LeverValues): LeverValues {
  const [, hi] = bounds(scenario, VOLUNTEERS, values);
  return { ...values, [VOLUNTEERS]: Math.min(values[VOLUNTEERS], hi) };
}

export type BurdenClass = "low" | "moderate" | "high";

export function likelyClass(probs: Record<string, number>): BurdenClass {
  const order: BurdenClass[] = ["low", "moderate", "high"];
  return order.reduce((best, c) => ((probs[c] ?? 0) > (probs[best] ?? 0) ? c : best), "low");
}

/** One line per lever that differs from the base plan: "11:00 AM start: 2 to 3". */
export function changeLines(option: OptionOut, base: OptionOut): string[] {
  return LEVERS.filter((l) => option.values[l.key] !== base.values[l.key]).map(
    (l) => `${l.label}: ${base.values[l.key]} to ${option.values[l.key]}`,
  );
}

const signed = (n: number) => (n > 0 ? `+${n}` : `${n}`);

/** Short summary of an option's staff changes, e.g. "+1 at 11:00, +1 outside". */
export function changeSummary(option: OptionOut): string {
  const parts = LEVERS.filter((l) => (option.changes[l.key] ?? 0) !== 0).map((l) =>
    l.key === VOLUNTEERS
      ? `${option.values[l.key]} willing to stay`
      : `${signed(option.changes[l.key] ?? 0)} at ${l.short}`,
  );
  return parts.length ? parts.join(", ") : "Plan as it is";
}

/** Hours from overtime numbers, one decimal. */
export const hours = (v: number) => v.toFixed(1);

/** Points of the trade-off chart: options with the selected number of volunteers. */
export function chartPoints(scenario: ScenarioOut, volunteers: number) {
  const pareto = new Set(scenario.pareto_ids);
  return scenario.options
    .filter((o) => o.values[VOLUNTEERS] === volunteers)
    .map((o) => ({
      id: o.id,
      x: o.added_staff_hours,
      y: o.ot_p50,
      kind:
        o.id === scenario.minimum_change_id
          ? ("minimum" as const)
          : o.low_confidence
            ? ("low" as const)
            : pareto.has(o.id)
              ? ("pareto" as const)
              : ("other" as const),
      option: o,
    }));
}
