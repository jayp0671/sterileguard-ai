/**
 * Plan Tomorrow form model, generated from the OpenAPI contract (SG-11). Field names, labels,
 * sections, ranges and descriptions all come from packages/data/src/sg_data/schema.py through
 * openapi.json, so the form can never drift from the API's validation.
 */
import spec from "@sg/contracts/openapi.json";
import { z } from "zod";

export type FieldKind = "int" | "bool" | "enum";
export type PlanGroup = "demand" | "staffing" | "equipment" | "carryover";

export type PlanField = {
  name: string;
  label: string;
  group: PlanGroup;
  kind: FieldKind;
  description: string;
  unit?: string;
  min?: number;
  max?: number;
  options?: string[];
  required: boolean;
  tier: number;
};

type JsonSchema = {
  type?: string;
  anyOf?: JsonSchema[];
  enum?: string[];
  const?: string;
  minimum?: number;
  maximum?: number;
  description?: string;
  unit?: string;
  tier?: number;
  "x-label"?: string;
  "x-group"?: PlanGroup;
};

export const GROUPS: { key: PlanGroup; label: string }[] = [
  { key: "demand", label: "Demand" },
  { key: "staffing", label: "Staffing by window" },
  { key: "equipment", label: "Equipment" },
  { key: "carryover", label: "Carryover" },
];

/** The two fields of the cross-field rule (schema.py `ot_available_ok`). */
export const OT_FIELD = "ot_available_staff";
export const MORNING_FIELD = "morning_staff_present";

const component = (name: string) =>
  (
    spec as unknown as {
      components: {
        schemas: Record<string, { properties: Record<string, JsonSchema>; required?: string[] }>;
      };
    }
  ).components.schemas[name];

function concrete(s: JsonSchema): JsonSchema {
  const branch = s.anyOf?.find((b) => b.type !== "null") ?? s;
  return {
    ...branch,
    description: s.description,
    unit: s.unit,
    tier: s.tier,
    "x-label": s["x-label"],
    "x-group": s["x-group"],
  };
}

export function planFields(): PlanField[] {
  // PlanPut is ShiftPlanIn plus status and backfill (those carry no x-label and are dropped).
  const schema = component("PlanPut");
  if (!schema) throw new Error("PlanPut is missing from openapi.json");
  const required = new Set(schema.required ?? []);
  return Object.entries(schema.properties)
    .map(([name, raw]) => {
      const s = concrete(raw);
      const kind: FieldKind = s.enum ? "enum" : s.type === "boolean" ? "bool" : "int";
      return {
        name,
        label: s["x-label"] ?? name,
        group: s["x-group"] ?? "demand",
        kind,
        description: s.description ?? "",
        unit: s.unit,
        min: s.minimum,
        max: s.maximum,
        options: s.enum,
        required: required.has(name),
        tier: s.tier ?? 0,
      };
    })
    .filter((f) => f.label !== f.name);
}

export type PlanValues = Record<string, number | boolean | string | null>;

/** zod schema with the same ranges as the API, plus the cross-field overtime rule. */
export function planSchema(fields: PlanField[] = planFields()) {
  const shape: Record<string, z.ZodType> = {};
  for (const f of fields) {
    let t: z.ZodType;
    if (f.kind === "int") {
      let n = z
        .number({ error: `${f.label} must be a whole number` })
        .int(`${f.label} must be a whole number`);
      if (f.min !== undefined) n = n.min(f.min, `${f.label} must be at least ${f.min}`);
      if (f.max !== undefined) n = n.max(f.max, `${f.label} must be at most ${f.max}`);
      t = n;
    } else if (f.kind === "bool") {
      t = z.boolean();
    } else {
      t = z.enum(f.options as [string, ...string[]]);
    }
    shape[f.name] = f.required ? t : t.nullable().optional();
  }
  return z.object(shape).superRefine((v, ctx) => {
    const ot = v[OT_FIELD];
    const morning = v[MORNING_FIELD];
    if (typeof ot === "number" && typeof morning === "number" && ot > morning) {
      ctx.addIssue({
        code: "custom",
        path: [OT_FIELD],
        message: "Staff willing to stay cannot exceed 7:00 AM staff",
      });
    }
  });
}

/** Field errors keyed by field name, from zod or from a problem+json `errors` list. */
export function fieldErrors(values: PlanValues): Record<string, string> {
  const result = planSchema().safeParse(values);
  if (result.success) return {};
  const out: Record<string, string> = {};
  for (const issue of result.error.issues) {
    const key = String(issue.path[0] ?? "");
    if (key && !out[key]) out[key] = issue.message;
  }
  return out;
}

/** Next workday (Mon to Fri) after today in the given time zone, as YYYY-MM-DD. */
export function nextWorkday(now = new Date(), timeZone = "America/New_York"): string {
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
  const d = new Date(`${today}T12:00:00Z`);
  do {
    d.setUTCDate(d.getUTCDate() + 1);
  } while (d.getUTCDay() === 0 || d.getUTCDay() === 6);
  return d.toISOString().slice(0, 10);
}
