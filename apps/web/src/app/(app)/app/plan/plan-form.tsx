"use client";

import { ApiError } from "@sg/contracts";
import { Lock, Minus, Plus, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { ErrorState, PageHeader } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { type PlanOut, type PlanPut, usePlan, useSavePlan } from "@/hooks/use-plan";
import {
  fieldErrors,
  GROUPS,
  nextWorkday,
  type PlanField,
  type PlanValues,
  planFields,
} from "@/lib/plan-fields";
import { cn } from "@/lib/utils";

export const AUTOSAVE_MS = 10_000;
const FIELDS = planFields();

/** Plain-language source for a suggested value (from PlanOut.sources). */
export function describeSource(source: string | undefined): string | null {
  if (!source || source === "saved" || source === "none") return null;
  if (source === "default") return "Department default";
  if (source.startsWith("settings:")) return `Department setting (${source.slice(9)})`;
  if (source.startsWith("history:")) {
    const text = source.slice(8);
    return text.charAt(0).toUpperCase() + text.slice(1);
  }
  return source;
}

function SuggestedTag({ source }: { source: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="rounded-sm border border-status-info-border bg-status-info-bg px-1.5 text-xs text-status-info"
        >
          Suggested
        </button>
      </TooltipTrigger>
      <TooltipContent>{source}</TooltipContent>
    </Tooltip>
  );
}

function FieldControl({
  field,
  value,
  error,
  readOnly,
  onChange,
}: {
  field: PlanField;
  value: PlanValues[string];
  error?: string;
  readOnly: boolean;
  onChange: (v: PlanValues[string]) => void;
}) {
  const id = `plan-${field.name}`;
  const errId = `${id}-error`;
  const describedBy = error ? errId : undefined;
  if (field.kind === "bool") {
    return (
      <label htmlFor={id} className="flex min-h-11 items-center gap-3 text-sm">
        <input
          id={id}
          type="checkbox"
          className="size-5 accent-[var(--primary)]"
          checked={Boolean(value)}
          disabled={readOnly}
          onChange={(e) => onChange(e.target.checked)}
        />
        {field.label}
      </label>
    );
  }
  if (field.kind === "enum") {
    return (
      <select
        id={id}
        aria-invalid={Boolean(error)}
        aria-describedby={describedBy}
        className="h-11 w-full rounded-md border border-input bg-card px-3 text-sm"
        value={String(value ?? "")}
        disabled={readOnly}
        onChange={(e) => onChange(e.target.value)}
      >
        {(field.options ?? []).map((o) => (
          <option key={o} value={o}>
            {o.replace("_", " ")}
          </option>
        ))}
      </select>
    );
  }
  const num = typeof value === "number" ? value : null;
  const step = (d: number) => {
    const next = (num ?? field.min ?? 0) + d;
    onChange(Math.min(field.max ?? next, Math.max(field.min ?? next, next)));
  };
  return (
    <div className="flex items-center gap-1">
      {readOnly ? null : (
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="size-11"
          aria-label={`Decrease ${field.label}`}
          onClick={() => step(-1)}
        >
          <Minus />
        </Button>
      )}
      <Input
        id={id}
        inputMode="numeric"
        className="tabular h-11 w-24 text-center"
        aria-invalid={Boolean(error)}
        aria-describedby={describedBy}
        readOnly={readOnly}
        value={num ?? ""}
        onChange={(e) => {
          const raw = e.target.value.trim();
          onChange(raw === "" ? null : Number(raw));
        }}
      />
      {readOnly ? null : (
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="size-11"
          aria-label={`Increase ${field.label}`}
          onClick={() => step(1)}
        >
          <Plus />
        </Button>
      )}
      {field.unit ? <span className="ms-1 text-13 text-muted-foreground">{field.unit}</span> : null}
    </div>
  );
}

function serverErrors(err: unknown): Record<string, string> {
  if (!(err instanceof ApiError) || !err.errors) return {};
  const out: Record<string, string> = {};
  for (const e of err.errors) {
    const name = String(e.loc[e.loc.length - 1] ?? "");
    if (name) out[name] = e.msg;
  }
  return out;
}

export function PlanForm({
  departmentId,
  canEdit,
  initialDate = nextWorkday(),
}: {
  departmentId: string | undefined;
  canEdit: boolean;
  initialDate?: string;
}) {
  const [date, setDate] = useState(initialDate);
  const plan = usePlan(departmentId, date);
  const save = useSavePlan();
  const [values, setValues] = useState<PlanValues>({});
  const [dirty, setDirty] = useState(false);
  const [conflict, setConflict] = useState(false);
  const keyRef = useRef<string>(crypto.randomUUID());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const reset = useCallback((p: PlanOut | undefined) => {
    setValues(p ? { ...(p.values as PlanValues) } : {});
    setDirty(false);
    setConflict(false);
  }, []);

  useEffect(() => {
    reset(plan.data);
  }, [plan.data, reset]);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const errors = useMemo(
    () => ({ ...serverErrors(save.error), ...(dirty ? fieldErrors(values) : {}) }),
    [values, dirty, save.error],
  );

  const persist = useCallback(
    (status: "draft" | "final", current: PlanValues) => {
      if (!departmentId || Object.keys(fieldErrors(current)).length > 0) return;
      const body = { ...current, status } as PlanPut;
      save.mutate(
        { departmentId, date, body, idempotencyKey: keyRef.current },
        {
          onSuccess: () => {
            setDirty(false);
            toast.success(status === "final" ? "Plan finalized" : "Draft saved");
          },
          onError: (err) => {
            if (err instanceof ApiError && err.status === 409) setConflict(true);
          },
        },
      );
    },
    [departmentId, date, save],
  );

  const change = (name: string, v: PlanValues[string]) => {
    const next = { ...values, [name]: v };
    setValues(next);
    setDirty(true);
    keyRef.current = crypto.randomUUID(); // a new edit is a new request
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => persist("draft", next), AUTOSAVE_MS);
  };

  const finalize = () => {
    if (timer.current) clearTimeout(timer.current);
    persist("final", values);
  };

  const readOnly = !canEdit;
  const p = plan.data;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={p?.status === "final" ? "Final plan" : p?.suggested ? "Suggested plan" : "Draft"}
        title={canEdit ? "Plan tomorrow" : "Tomorrow's plan"}
        description="Inputs known before 7:00 AM. The forecast uses only these."
        actions={
          <div className="flex items-end gap-2">
            <label className="flex flex-col gap-1 text-13">
              <span className="engraved">Date</span>
              <Input
                type="date"
                className="h-11"
                value={date}
                onChange={(e) => e.target.value && setDate(e.target.value)}
              />
            </label>
            {canEdit ? (
              <Button className="h-11" onClick={finalize} disabled={save.isPending || !p}>
                Finalize plan
              </Button>
            ) : null}
          </div>
        }
      />
      {readOnly ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Lock className="size-4" aria-hidden /> Read only. Supervisors and department admins edit
          the plan.
        </p>
      ) : null}
      {conflict ? (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-3 rounded-lg border border-status-warning-border bg-status-warning-bg p-3 text-sm text-status-warning"
        >
          This plan changed somewhere else, or the same save was sent twice with different data.
          <Button
            variant="outline"
            className="h-11"
            onClick={() => void plan.refetch().then((r) => reset(r.data))}
          >
            <RotateCcw /> Reload the latest plan
          </Button>
        </div>
      ) : null}
      {plan.isPending ? (
        <div className="grid gap-4 md:grid-cols-2" aria-busy="true">
          {GROUPS.map((g) => (
            <Skeleton key={g.key} className="h-48" />
          ))}
        </div>
      ) : plan.isError ? (
        <ErrorState
          title="Could not load the plan"
          detail={plan.error instanceof ApiError ? plan.error.detail : "Check your connection."}
          requestId={plan.error instanceof ApiError ? plan.error.requestId : undefined}
          onRetry={() => void plan.refetch()}
        />
      ) : (
        <form
          className="grid gap-4 md:grid-cols-2"
          aria-label="Plan inputs"
          onSubmit={(e) => {
            e.preventDefault();
            finalize();
          }}
        >
          {GROUPS.map((g) => (
            <fieldset key={g.key} className="flex flex-col gap-3 rounded-lg border bg-card p-4">
              <legend className="engraved px-1">{g.label}</legend>
              {FIELDS.filter((f) => f.group === g.key).map((f) => {
                const source = describeSource(p?.sources?.[f.name]);
                return (
                  <div key={f.name} className="flex flex-col gap-1">
                    {f.kind === "bool" ? null : (
                      <div className="flex items-center gap-2">
                        <label htmlFor={`plan-${f.name}`} className="text-sm font-medium">
                          {f.label}
                        </label>
                        {source && !dirty ? <SuggestedTag source={source} /> : null}
                      </div>
                    )}
                    <FieldControl
                      field={f}
                      value={values[f.name] ?? null}
                      error={errors[f.name]}
                      readOnly={readOnly}
                      onChange={(v) => change(f.name, v)}
                    />
                    {errors[f.name] ? (
                      <p id={`plan-${f.name}-error`} className={cn("text-13 text-status-critical")}>
                        {errors[f.name]}
                      </p>
                    ) : null}
                  </div>
                );
              })}
            </fieldset>
          ))}
        </form>
      )}
      {save.isPending ? (
        <p className="text-13 text-muted-foreground" aria-live="polite">
          Saving…
        </p>
      ) : dirty && canEdit ? (
        <p className="text-13 text-muted-foreground" aria-live="polite">
          Unsaved changes. Drafts save 10 seconds after your last change.
        </p>
      ) : null}
    </div>
  );
}
