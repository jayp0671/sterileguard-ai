"use client";

import { ApiError } from "@sg/contracts";
import { Check, CloudOff, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useSaveShift, useTransition } from "@/hooks/use-shifts";
import { planFields } from "@/lib/plan-fields";
import {
  clearDraft,
  draftBody,
  draftOvertime,
  emptyDraft,
  hoursPast,
  loadDraft,
  type ShiftDraft,
  saveDraft,
} from "@/lib/shift-log";
import { cn } from "@/lib/utils";

const STEPS = ["Date", "Overtime", "After the shift", "Notes and review"] as const;
const LEADS = ["supervisor", "dept_admin"];
const SERVER_SAVE_MS = 1500;

function todayIso(timeZone = "America/New_York"): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function problemText(err: unknown): string {
  if (err instanceof ApiError) return err.detail ?? err.title;
  return "Could not reach the server. The draft is kept on this device.";
}

export function ShiftForm({ departmentId, roles }: { departmentId: string; roles: string[] }) {
  const router = useRouter();
  const canBackfill = roles.some((r) => LEADS.includes(r));
  const today = todayIso();
  const [d, setD] = useState<ShiftDraft>(() => loadDraft(departmentId) ?? emptyDraft(today));
  const [restored] = useState(() => loadDraft(departmentId) !== null);
  const save = useSaveShift(departmentId);
  const transition = useTransition(departmentId);
  const [serverState, setServerState] = useState<"idle" | "saved" | "offline" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const update = (patch: Partial<ShiftDraft>) =>
    setD((cur) => ({ ...cur, ...patch, savedAt: new Date().toISOString() }));

  const backfillFields = useMemo(
    () => planFields().filter((f) => f.kind === "int" && f.tier <= 2),
    [],
  );
  const overtime = draftOvertime(d);

  // Every change is kept in this browser at once.
  useEffect(() => saveDraft(departmentId, d), [departmentId, d]);

  // ...and on the server shortly after, once there is an overtime value. A backfill waits for
  // the review step: its plan is created together with the first save.
  const saving = useRef(false);
  useEffect(() => {
    if (overtime === null || d.backfill || !d.savedAt) return;
    const t = setTimeout(() => {
      if (saving.current) return;
      saving.current = true;
      save.mutate(
        { id: d.serverId, shiftDate: d.shiftDate, fields: draftBody(d) },
        {
          onSuccess: (s) => {
            setServerState("saved");
            setError(null);
            if (!d.serverId) setD((cur) => ({ ...cur, serverId: s.id }));
          },
          onError: (err) => {
            setServerState(err instanceof ApiError ? "error" : "offline");
            if (err instanceof ApiError) setError(problemText(err));
          },
          onSettled: () => {
            saving.current = false;
          },
        },
      );
    }, SERVER_SAVE_MS);
    return () => clearTimeout(t);
  }, [d.savedAt]);

  const stepValid = [
    d.shiftDate !== "" && d.shiftDate <= today,
    overtime !== null,
    true,
    !d.backfill || backfillFields.filter((f) => f.required).every((f) => d.plan[f.name]),
  ];

  async function submit() {
    setError(null);
    try {
      const plan = d.backfill
        ? Object.fromEntries(
            Object.entries(d.plan)
              .filter(([, v]) => v !== "")
              .map(([k, v]) => [k, Number(v)]),
          )
        : null;
      const saved = await save.mutateAsync({
        id: d.serverId,
        shiftDate: d.shiftDate,
        fields: draftBody(d),
        plan,
      });
      await transition.mutateAsync({ id: saved.id, action: "submit" });
      clearDraft(departmentId);
      toast.success("Shift submitted for approval");
      router.push(`/app/history?shift=${saved.id}`);
    } catch (err) {
      setError(problemText(err));
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
      <PageHeader
        eyebrow="Log a shift"
        title="What happened today"
        description="Overtime of the morning operation after 3:00 PM, and the context that explains it."
      />

      <ol className="grid grid-cols-4 gap-2" aria-label="Steps">
        {STEPS.map((label, i) => (
          <li key={label}>
            <button
              type="button"
              onClick={() =>
                i <= d.step || stepValid.slice(0, i).every(Boolean) ? update({ step: i }) : null
              }
              aria-current={i === d.step ? "step" : undefined}
              className={cn(
                "flex min-h-11 w-full flex-col items-start gap-1 border-t-2 pt-2 text-start text-13",
                i === d.step
                  ? "border-primary text-foreground"
                  : i < d.step
                    ? "border-primary/40 text-muted-foreground"
                    : "border-border text-muted-foreground",
              )}
            >
              <span className="tabular">Step {i + 1}</span>
              <span className="font-medium">{label}</span>
            </button>
          </li>
        ))}
      </ol>

      {restored && d.step === 0 && d.savedAt ? (
        <p className="rounded-md border bg-accent px-3 py-2 text-sm">
          We restored your unsent draft from this device.
        </p>
      ) : null}

      <section className="flex flex-col gap-5 rounded-lg border bg-card p-4 sm:p-6">
        {d.step === 0 ? (
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="shift-date">Shift date</Label>
              <Input
                id="shift-date"
                type="date"
                max={today}
                value={d.shiftDate}
                disabled={Boolean(d.serverId)}
                onChange={(e) => update({ shiftDate: e.target.value })}
                className="h-12 max-w-xs text-base"
              />
              <p className="text-13 text-muted-foreground">
                {d.serverId
                  ? "This draft is saved for this date. Start a new log to pick another date."
                  : "Today or an earlier day."}
              </p>
            </div>
            {canBackfill ? (
              <label className="flex min-h-11 items-start gap-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-1 size-5"
                  checked={d.backfill}
                  disabled={Boolean(d.serverId)}
                  onChange={(e) => update({ backfill: e.target.checked })}
                />
                <span>
                  <span className="font-medium">Log a past day</span>
                  <span className="block text-muted-foreground">
                    Also enter that day's plan (patients and staff), for a real day that has no plan
                    yet.
                  </span>
                </span>
              </label>
            ) : null}
          </div>
        ) : null}

        {d.step === 1 ? <OvertimeStep d={d} update={update} total={overtime} /> : null}

        {d.step === 2 ? (
          <div className="grid gap-4 sm:grid-cols-3">
            <NumberField
              id="emergency"
              label="Emergency and intake patients"
              value={d.emergency}
              onChange={(v) => update({ emergency: v })}
            />
            <NumberField
              id="returned"
              label="Returned unused (estimate)"
              value={d.returnedUnused}
              onChange={(v) => update({ returnedUnused: v })}
            />
            <NumberField
              id="downtime"
              label="Equipment downtime (minutes)"
              value={d.downtime}
              onChange={(v) => update({ downtime: v })}
            />
            <p className="text-13 text-muted-foreground sm:col-span-3">
              Known only after the shift, so they explain the day but never feed the forecast.
            </p>
          </div>
        ) : null}

        {d.step === 3 ? (
          <div className="flex flex-col gap-5">
            {d.backfill ? (
              <fieldset className="flex flex-col gap-3">
                <legend className="engraved mb-2">That day's plan</legend>
                <div className="grid gap-3 sm:grid-cols-2">
                  {backfillFields.map((f) => (
                    <NumberField
                      key={f.name}
                      id={`plan-${f.name}`}
                      label={`${f.label}${f.required ? "" : " (optional)"}`}
                      value={d.plan[f.name] ?? ""}
                      onChange={(v) => update({ plan: { ...d.plan, [f.name]: v } })}
                    />
                  ))}
                </div>
              </fieldset>
            ) : null}
            <div className="flex flex-col gap-2">
              <Label htmlFor="notes">Notes (optional)</Label>
              <p id="notes-warning" className="text-sm font-medium text-status-warning">
                Do not enter patient or employee names.
              </p>
              <Textarea
                id="notes"
                aria-describedby="notes-warning"
                maxLength={500}
                rows={4}
                value={d.notes}
                onChange={(e) => update({ notes: e.target.value })}
                className="text-base"
              />
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-md border bg-muted/40 p-3 text-sm">
              <dt className="text-muted-foreground">Date</dt>
              <dd className="tabular">{d.shiftDate}</dd>
              <dt className="text-muted-foreground">Overtime</dt>
              <dd className="tabular">{overtime === null ? "–" : `${overtime} h`}</dd>
              <dt className="text-muted-foreground">Emergency and intake</dt>
              <dd className="tabular">{d.emergency || "–"}</dd>
              <dt className="text-muted-foreground">Returned unused</dt>
              <dd className="tabular">{d.returnedUnused || "–"}</dd>
              <dt className="text-muted-foreground">Downtime</dt>
              <dd className="tabular">{d.downtime ? `${d.downtime} min` : "–"}</dd>
            </dl>
          </div>
        ) : null}

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
            {error.includes("/app/history?shift=") ? (
              <>
                {" "}
                <Link className="underline" href={error.slice(error.indexOf("/app/history"))}>
                  Open it
                </Link>
              </>
            ) : null}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-2 border-t pt-4">
          <span className="text-13 text-muted-foreground" aria-live="polite">
            {serverState === "saved" ? (
              <span className="inline-flex items-center gap-1">
                <Check className="size-4" aria-hidden /> Draft saved
              </span>
            ) : serverState === "offline" ? (
              <span className="inline-flex items-center gap-1">
                <CloudOff className="size-4" aria-hidden /> Saved on this device only
              </span>
            ) : d.backfill ? (
              "Saved on this device until you submit"
            ) : null}
          </span>
          <div className="ms-auto flex gap-2">
            {d.step > 0 ? (
              <Button
                variant="outline"
                className="min-h-11"
                onClick={() => update({ step: d.step - 1 })}
              >
                Back
              </Button>
            ) : null}
            {d.step < STEPS.length - 1 ? (
              <Button
                className="min-h-11"
                disabled={!stepValid[d.step]}
                onClick={() => update({ step: d.step + 1 })}
              >
                Next
              </Button>
            ) : (
              <Button
                className="min-h-11"
                disabled={!stepValid.every(Boolean) || save.isPending || transition.isPending}
                onClick={() => void submit()}
              >
                {save.isPending || transition.isPending ? "Submitting" : "Submit for approval"}
              </Button>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function NumberField({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        inputMode="numeric"
        type="number"
        min={0}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-12 text-base"
      />
    </div>
  );
}

function OvertimeStep({
  d,
  update,
  total,
}: {
  d: ShiftDraft;
  update: (p: Partial<ShiftDraft>) => void;
  total: number | null;
}) {
  return (
    <div className="flex flex-col gap-4">
      <div role="radiogroup" aria-label="How to enter overtime" className="flex flex-wrap gap-2">
        {(
          [
            ["total", "Enter the total"],
            ["helper", "Who stayed past 3 PM?"],
          ] as const
        ).map(([mode, label]) => (
          <Button
            key={mode}
            role="radio"
            aria-checked={d.otMode === mode}
            variant={d.otMode === mode ? "default" : "outline"}
            className="min-h-11"
            onClick={() => update({ otMode: mode })}
          >
            {label}
          </Button>
        ))}
      </div>

      {d.otMode === "total" ? (
        <div className="flex flex-col gap-2">
          <Label htmlFor="ot-total">Overtime labor-hours past 3:00 PM</Label>
          <Input
            id="ot-total"
            inputMode="decimal"
            type="number"
            min={0}
            max={60}
            step={0.25}
            value={d.otTotal}
            onChange={(e) => update({ otTotal: e.target.value })}
            className="h-12 max-w-xs text-base"
          />
          <p className="text-13 text-muted-foreground">
            Morning-operation staff only; outside support is not overtime.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted-foreground">
            Add one row per person who stayed, with the time they left. No names: only the total is
            saved.
          </p>
          <ul className="flex flex-col gap-2">
            {d.endTimes.map((end, i) => {
              const h = hoursPast(end);
              return (
                <li key={i} className="flex items-center gap-2">
                  <Label htmlFor={`end-${i}`} className="w-20 shrink-0 text-13">
                    Left at
                  </Label>
                  <Input
                    id={`end-${i}`}
                    type="time"
                    value={end}
                    onChange={(e) =>
                      update({
                        endTimes: d.endTimes.map((x, j) => (j === i ? e.target.value : x)),
                      })
                    }
                    className="h-12 w-36 text-base"
                  />
                  <span className="tabular w-16 text-sm">
                    {end && h !== null ? `${h.toFixed(2).replace(/\.?0+$/, "")} h` : ""}
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-11"
                    aria-label={`Remove row ${i + 1}`}
                    disabled={d.endTimes.length === 1}
                    onClick={() => update({ endTimes: d.endTimes.filter((_, j) => j !== i) })}
                  >
                    <Trash2 aria-hidden />
                  </Button>
                </li>
              );
            })}
          </ul>
          <Button
            variant="outline"
            className="min-h-11 self-start"
            onClick={() => update({ endTimes: [...d.endTimes, ""] })}
          >
            <Plus aria-hidden /> Add a person
          </Button>
        </div>
      )}
      <p className="text-base" aria-live="polite">
        Total overtime:{" "}
        <span className="tabular text-lg font-medium">{total === null ? "–" : `${total} h`}</span>
      </p>
    </div>
  );
}
