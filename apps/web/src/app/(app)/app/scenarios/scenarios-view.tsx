"use client";

import { ApiError } from "@sg/contracts";
import {
  CalendarClock,
  Check,
  FlaskConical,
  Minus,
  Pin,
  PinOff,
  Plus,
  RefreshCw,
  Sparkles,
  TriangleAlert,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { BurdenBadge } from "@/components/burden-badge";
import { MetricCard } from "@/components/metric-card";
import { TradeoffChart } from "@/components/scenarios/tradeoff-chart";
import { EmptyState, ErrorState, PageHeader } from "@/components/states";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { type PlanOut, usePlan } from "@/hooks/use-plan";
import {
  type OptionOut,
  type ScenarioOut,
  useApplyScenario,
  useLatestScenario,
  useRunScenario,
} from "@/hooks/use-scenarios";
import { nextWorkday } from "@/lib/plan-fields";
import {
  bounds,
  changeLines,
  changeSummary,
  DEBOUNCE_MS,
  findOption,
  hours,
  LEVERS,
  type LeverKey,
  type LeverValues,
  leverValues,
  likelyClass,
  normalize,
  VOLUNTEERS,
} from "@/lib/scenarios";
import { cn } from "@/lib/utils";
import { EDITORS, longDate } from "../forecast-home";

const MAX_PINNED = 3;

function problem(err: unknown): { detail?: string; requestId?: string } {
  if (err instanceof ApiError) return { detail: err.detail ?? err.title, requestId: err.requestId };
  return { detail: err instanceof Error ? err.message : undefined };
}

export function ScenariosView({
  departmentId,
  roles,
  date = nextWorkday(),
}: {
  departmentId: string | undefined;
  roles: string[];
  date?: string;
}) {
  const canRun = roles.some((r) => EDITORS.includes(r));
  const plan = usePlan(departmentId, date);
  const latest = useLatestScenario(departmentId, date);
  const runner = useRunScenario();
  const run = () => departmentId && runner.mutate({ departmentId, date });

  const scenario = latest.data;
  const hasPlan = plan.data !== undefined && !plan.data.suggested;
  const stale = Boolean(
    scenario && plan.data?.updated_at && plan.data.updated_at > scenario.created_at,
  );

  // A supervisor opening the page with a saved plan and no run gets one straight away.
  const autoRun = canRun && hasPlan && latest.data === null && runner.isIdle;
  useEffect(() => {
    if (autoRun && departmentId) runner.mutate({ departmentId, date });
  }, [autoRun, departmentId, date, runner]);

  const loading = plan.isPending || latest.isPending || (runner.isPending && !scenario);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Staffing scenarios"
        title={`What if, ${longDate(date)}`}
        description="Change staff by start time and see predicted overtime update. The recommendation is the smallest change that meets the department's target."
        actions={
          canRun && scenario ? (
            <Button
              variant="outline"
              className="min-h-11"
              onClick={run}
              disabled={runner.isPending}
            >
              <RefreshCw className={runner.isPending ? "animate-spin" : undefined} aria-hidden />
              {runner.isPending ? "Running" : "Run again"}
            </Button>
          ) : null
        }
      />

      {runner.isError ? (
        <ErrorState
          title={
            runner.error instanceof ApiError && runner.error.status === 503
              ? "The forecast model is not loaded"
              : "The scenarios could not be computed"
          }
          {...problem(runner.error)}
          onRetry={run}
        />
      ) : null}

      {stale ? (
        <p className="rounded-md border border-status-warning/40 bg-status-warning/5 px-3 py-2 text-sm text-status-warning">
          The plan changed after these scenarios were computed.
          {canRun ? " Run them again before applying an option." : ""}
        </p>
      ) : null}

      {loading ? (
        <ScenariosSkeleton />
      ) : latest.isError ? (
        <ErrorState
          title="The scenarios could not be loaded"
          {...problem(latest.error)}
          onRetry={() => void latest.refetch()}
        />
      ) : scenario ? (
        <ScenarioBody
          key={scenario.id}
          scenario={scenario}
          plan={plan.data}
          canApply={canRun && !stale}
          departmentId={departmentId ?? ""}
          date={date}
        />
      ) : !hasPlan ? (
        <EmptyState
          icon={CalendarClock}
          title="No plan for tomorrow yet"
          description="Scenarios start from tomorrow's saved plan: patients, staff by start time and equipment."
          action={
            <Button asChild className="min-h-11">
              <Link href="/app/plan">{canRun ? "Plan tomorrow" : "View tomorrow's plan"}</Link>
            </Button>
          }
        />
      ) : (
        <EmptyState
          icon={FlaskConical}
          title="No scenarios yet"
          description={
            canRun
              ? "Compute the staffing options for tomorrow's plan."
              : "A supervisor has not run scenarios for tomorrow yet."
          }
          action={
            canRun ? (
              <Button className="min-h-11" onClick={run} disabled={runner.isPending}>
                Run scenarios
              </Button>
            ) : undefined
          }
        />
      )}
    </div>
  );
}

function ScenarioBody({
  scenario,
  plan,
  canApply,
  departmentId,
  date,
}: {
  scenario: ScenarioOut;
  plan: PlanOut | undefined;
  canApply: boolean;
  departmentId: string;
  date: string;
}) {
  const start =
    (scenario.applied_option_id &&
      scenario.options.find((o) => o.id === scenario.applied_option_id)) ||
    scenario.base;
  const [values, setValues] = useState<LeverValues>(() => leverValues(start));
  const [shown, setShown] = useState<LeverValues>(values);
  const [pinned, setPinned] = useState<string[]>([]);
  const [confirming, setConfirming] = useState(false);

  // Recompute 400 ms after the last stepper change.
  useEffect(() => {
    const t = setTimeout(() => setShown(values), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [values]);

  const option = findOption(scenario, shown);
  const updating = LEVERS.some((l) => values[l.key] !== shown[l.key]);
  const recommended = scenario.options.find((o) => o.id === scenario.minimum_change_id);
  const show = (o: OptionOut) => {
    const v = leverValues(o);
    setValues(v);
    setShown(v);
  };
  const step = (key: LeverKey, delta: number) =>
    setValues((v) => normalize(scenario, { ...v, [key]: v[key] + delta }));
  const togglePin = (id: string) =>
    setPinned((p) =>
      p.includes(id) ? p.filter((x) => x !== id) : p.length < MAX_PINNED ? [...p, id] : p,
    );

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <section aria-labelledby="levers-heading" className="flex flex-col gap-4">
          <PlanSummary plan={plan} scenario={scenario} />
          <div className="flex flex-col gap-1 rounded-lg border bg-card p-4">
            <h2 id="levers-heading" className="engraved mb-2">
              Staff by start time
            </h2>
            {LEVERS.map((l) => {
              const [lo, hi] = bounds(scenario, l.key, values);
              return (
                <Stepper
                  key={l.key}
                  label={l.label}
                  value={values[l.key]}
                  base={scenario.base.values[l.key] ?? 0}
                  min={lo}
                  max={hi}
                  onStep={(d) => step(l.key, d)}
                  hint={
                    l.key === VOLUNTEERS
                      ? "A what-if: fewer people staying moves work to the next day, so it is never recommended."
                      : undefined
                  }
                />
              );
            })}
            <Button
              variant="ghost"
              className="mt-2 min-h-11 self-start"
              onClick={() => show(scenario.base)}
            >
              Reset to the plan
            </Button>
          </div>
        </section>

        <div className="flex flex-col gap-4">
          <Recommendation scenario={scenario} recommended={recommended} onShow={show} />
          {option ? (
            <ResultCard
              option={option}
              base={scenario.base}
              updating={updating}
              pinned={pinned.includes(option.id)}
              pinFull={pinned.length >= MAX_PINNED}
              onPin={() => togglePin(option.id)}
              canApply={canApply}
              applied={scenario.applied_option_id === option.id}
              onApply={() => setConfirming(true)}
            />
          ) : null}
        </div>
      </div>

      <TradeoffChart
        scenario={scenario}
        volunteers={shown[VOLUNTEERS]}
        selected={option}
        onSelect={show}
      />

      <Compare
        scenario={scenario}
        ids={pinned}
        onRemove={(id) => setPinned((p) => p.filter((x) => x !== id))}
        onShow={show}
      />

      {option ? (
        <ApplyDialog
          open={confirming}
          onOpenChange={setConfirming}
          scenario={scenario}
          option={option}
          departmentId={departmentId}
          date={date}
        />
      ) : null}
    </div>
  );
}

function PlanSummary({ plan, scenario }: { plan: PlanOut | undefined; scenario: ScenarioOut }) {
  const v = plan?.values;
  const items: [string, string][] = [
    ["Regular patients", String(v?.regular_patients ?? "–")],
    ["MF cases", String(v?.mf_cases ?? "–")],
    ["Clinic sessions", String(v?.student_clinic_sessions ?? "–")],
    ["Sterilizers up", String(v?.sterilizers_up ?? "–")],
  ];
  return (
    <section aria-label="Tomorrow's plan" className="rounded-lg border bg-card p-4">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="engraved">Tomorrow's plan</h2>
        <span className="text-13 text-muted-foreground">
          Plan as is:{" "}
          <span className="tabular text-foreground">{hours(scenario.base.ot_p50)} h</span>
        </span>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        {items.map(([k, val]) => (
          <div key={k} className="flex justify-between gap-2">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="tabular">{val}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Stepper({
  label,
  value,
  base,
  min,
  max,
  onStep,
  hint,
}: {
  label: string;
  value: number;
  base: number;
  min: number;
  max: number;
  onStep: (delta: number) => void;
  hint?: string;
}) {
  const diff = value - base;
  return (
    <div className="flex flex-col gap-1 border-b py-2 last:border-0">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium">{label}</span>
        <div role="group" aria-label={label} className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            className="size-11"
            onClick={() => onStep(-1)}
            disabled={value <= min}
            aria-label={`One fewer: ${label}`}
          >
            <Minus aria-hidden />
          </Button>
          <output
            aria-live="polite"
            className="tabular w-24 text-center text-lg font-medium"
            aria-label={`${label}: ${value}`}
          >
            {value}
            <span
              className={cn(
                "block whitespace-nowrap text-xs font-normal",
                diff === 0 ? "text-muted-foreground" : "text-primary",
              )}
            >
              {diff === 0 ? "as planned" : diff > 0 ? `+${diff}` : diff}
            </span>
          </output>
          <Button
            variant="outline"
            size="icon"
            className="size-11"
            onClick={() => onStep(1)}
            disabled={value >= max}
            aria-label={`One more: ${label}`}
          >
            <Plus aria-hidden />
          </Button>
        </div>
      </div>
      {hint ? <p className="text-13 text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

function Recommendation({
  scenario,
  recommended,
  onShow,
}: {
  scenario: ScenarioOut;
  recommended: OptionOut | undefined;
  onShow: (o: OptionOut) => void;
}) {
  const targetText =
    scenario.target.type === "p50_hours"
      ? `at most ${hours(scenario.target.value)} overtime hours`
      : `high-burden probability at most ${Math.round(scenario.target.value * 100)}%`;
  return (
    <section
      aria-labelledby="rec-heading"
      className={cn(
        "flex flex-col gap-2 rounded-lg border p-4",
        recommended ? "border-primary/40 bg-accent" : "bg-card",
      )}
    >
      <h2 id="rec-heading" className="engraved flex items-center gap-1.5">
        {recommended ? (
          <Sparkles className="size-4" aria-hidden />
        ) : (
          <TriangleAlert className="size-4" aria-hidden />
        )}
        {recommended ? "Recommended minimum change" : "No option meets the target"}
      </h2>
      <p className="text-base font-medium text-foreground">{scenario.message}</p>
      <p className="text-13 text-muted-foreground">Target: {targetText}.</p>
      {recommended && recommended.id !== scenario.base.id ? (
        <Button
          variant="outline"
          className="min-h-11 self-start"
          onClick={() => onShow(recommended)}
        >
          Show this option
        </Button>
      ) : null}
      <p className="engraved">{scenario.disclaimer}</p>
    </section>
  );
}

function ResultCard({
  option,
  base,
  updating,
  pinned,
  pinFull,
  onPin,
  canApply,
  applied,
  onApply,
}: {
  option: OptionOut;
  base: OptionOut;
  updating: boolean;
  pinned: boolean;
  pinFull: boolean;
  onPin: () => void;
  canApply: boolean;
  applied: boolean;
  onApply: () => void;
}) {
  const cls = likelyClass(option.burden_probs);
  const delta = Number((option.ot_p50 - base.ot_p50).toFixed(2));
  return (
    <MetricCard
      label="Predicted overtime with these staff"
      value={option.ot_p50}
      unit="overtime hours"
      range={[option.ot_p10, option.ot_p90]}
      delta={delta}
      deltaLabel="vs the plan"
      size="hero"
      className={cn("transition-opacity", updating && "opacity-60")}
      footer={
        <div className="flex flex-col gap-3 border-t pt-3" aria-live="polite" aria-busy={updating}>
          <p className="text-sm">
            Most likely <span className="tabular font-medium">{hours(option.ot_p50)}</span>, range{" "}
            <span className="tabular font-medium">{hours(option.ot_p10)}</span> to{" "}
            <span className="tabular font-medium">{hours(option.ot_p90)}</span> (80%). Plan as is:{" "}
            <span className="tabular">{hours(base.ot_p50)}</span>.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <BurdenBadge category={cls} probability={option.burden_probs[cls] ?? 0} />
            <span className="text-13 text-muted-foreground">
              Added staff-hours{" "}
              <span className="tabular text-foreground">{option.added_staff_hours}</span>
            </span>
          </div>
          <ProbabilityBars probs={option.burden_probs} />
          {option.low_confidence ? (
            <p className="flex items-start gap-1.5 text-13 text-status-warning">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
              Low confidence: this staffing is outside what the model saw in training.
            </p>
          ) : null}
          {option.what_if ? (
            <p className="text-13 text-muted-foreground">
              Changing who is willing to stay is a what-if, not a staffing change.
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              className="min-h-11"
              onClick={onPin}
              disabled={!pinned && pinFull}
              aria-pressed={pinned}
            >
              {pinned ? <PinOff aria-hidden /> : <Pin aria-hidden />}
              {pinned ? "Unpin" : pinFull ? "3 pinned" : "Pin to compare"}
            </Button>
            {canApply ? (
              <Button
                className="min-h-11"
                onClick={onApply}
                disabled={option.id === base.id || applied}
              >
                {applied ? <Check aria-hidden /> : null}
                {applied ? "Applied" : "Apply to tomorrow's plan"}
              </Button>
            ) : null}
          </div>
          <p className="engraved">Model estimate, not a guarantee.</p>
        </div>
      }
    />
  );
}

const CLASS_LABEL = { low: "Low", moderate: "Moderate", high: "High" } as const;

function ProbabilityBars({ probs }: { probs: Record<string, number> }) {
  return (
    <dl className="grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-1 text-13">
      {(["low", "moderate", "high"] as const).map((c) => {
        const p = probs[c] ?? 0;
        return (
          <div key={c} className="contents">
            <dt className="text-muted-foreground">{CLASS_LABEL[c]}</dt>
            <dd aria-hidden className="h-1.5 overflow-hidden rounded-full bg-muted">
              <span
                className="block h-full rounded-full bg-chart-1"
                style={{ width: `${p * 100}%` }}
              />
            </dd>
            <dd className="tabular text-end">{Math.round(p * 100)}%</dd>
          </div>
        );
      })}
    </dl>
  );
}

function Compare({
  scenario,
  ids,
  onRemove,
  onShow,
}: {
  scenario: ScenarioOut;
  ids: string[];
  onRemove: (id: string) => void;
  onShow: (o: OptionOut) => void;
}) {
  const options = ids
    .map((id) => scenario.options.find((o) => o.id === id))
    .filter((o): o is OptionOut => Boolean(o));
  return (
    <section
      aria-labelledby="compare-heading"
      className="flex flex-col gap-3 rounded-lg border bg-card p-4"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="compare-heading" className="font-medium">
          Compare
        </h2>
        <span className="text-13 text-muted-foreground">
          {options.length} of {MAX_PINNED} pinned
        </span>
      </div>
      {options.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Pin up to three options to see them side by side.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Pinned staffing options side by side</caption>
            <thead>
              <tr className="border-b">
                <th scope="col" className="engraved px-2 py-2 text-start">
                  <span className="sr-only">Measure</span>
                </th>
                {options.map((o, i) => (
                  <th key={o.id} scope="col" className="px-2 py-2 text-start align-top">
                    <div className="flex items-start justify-between gap-1">
                      <button
                        type="button"
                        className="min-h-11 text-start font-medium underline-offset-4 hover:underline"
                        onClick={() => onShow(o)}
                      >
                        Option {i + 1}
                        <span className="block text-13 font-normal text-muted-foreground">
                          {changeSummary(o)}
                        </span>
                      </button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-11"
                        onClick={() => onRemove(o.id)}
                        aria-label={`Unpin option ${i + 1}`}
                      >
                        <X aria-hidden />
                      </Button>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {LEVERS.map((l) => (
                <tr key={l.key} className="border-b">
                  <th
                    scope="row"
                    className="px-2 py-2 text-start font-normal text-muted-foreground"
                  >
                    {l.label}
                  </th>
                  {options.map((o) => (
                    <td key={o.id} className="tabular px-2 py-2">
                      {o.values[l.key]}
                    </td>
                  ))}
                </tr>
              ))}
              {(
                [
                  ["Most likely (h)", (o: OptionOut) => hours(o.ot_p50)],
                  ["80% range (h)", (o: OptionOut) => `${hours(o.ot_p10)} to ${hours(o.ot_p90)}`],
                  ["Burden", (o: OptionOut) => CLASS_LABEL[likelyClass(o.burden_probs)]],
                  ["Added staff-hours", (o: OptionOut) => String(o.added_staff_hours)],
                  ["Meets target", (o: OptionOut) => (o.meets_target ? "Yes" : "No")],
                ] as const
              ).map(([label, cell]) => (
                <tr key={label} className="border-b last:border-0">
                  <th
                    scope="row"
                    className="px-2 py-2 text-start font-normal text-muted-foreground"
                  >
                    {label}
                  </th>
                  {options.map((o) => (
                    <td key={o.id} className="tabular px-2 py-2">
                      {cell(o)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="engraved mt-2">Model estimate, not a guarantee.</p>
        </div>
      )}
    </section>
  );
}

function ApplyDialog({
  open,
  onOpenChange,
  scenario,
  option,
  departmentId,
  date,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scenario: ScenarioOut;
  option: OptionOut;
  departmentId: string;
  date: string;
}) {
  const apply = useApplyScenario();
  const lines = changeLines(option, scenario.base);
  const confirm = () =>
    apply.mutate(
      { departmentId, date, scenarioId: scenario.id, optionId: option.id },
      {
        onSuccess: (out) => {
          onOpenChange(false);
          toast.success(
            `Plan updated. New forecast: ${hours(out.forecast.ot_p50)} overtime hours (most likely).`,
          );
        },
      },
    );
  const planChanged = apply.error instanceof ApiError && apply.error.status === 409;
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) apply.reset();
        onOpenChange(o);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Apply to tomorrow's plan?</DialogTitle>
          <DialogDescription>
            These changes are saved to the plan for {longDate(date)}, and the forecast is
            recomputed.
          </DialogDescription>
        </DialogHeader>
        <ul className="flex flex-col gap-1 rounded-md border bg-muted/40 p-3 text-sm">
          {lines.map((line) => (
            <li key={line} className="tabular">
              {line}
            </li>
          ))}
        </ul>
        <p className="text-sm">
          Predicted overtime: <span className="tabular">{hours(scenario.base.ot_p50)}</span> to{" "}
          <span className="tabular font-medium">{hours(option.ot_p50)}</span> hours (most likely).
        </p>
        {option.low_confidence ? (
          <p className="text-13 text-status-warning">
            Low confidence: this staffing is outside what the model saw in training.
          </p>
        ) : null}
        <p className="engraved">Model estimate, not a guarantee.</p>
        {apply.isError ? (
          <p role="alert" className="text-sm text-destructive">
            {planChanged
              ? "The plan changed after these scenarios were computed. Close this and run them again."
              : (problem(apply.error).detail ?? "The plan could not be updated.")}
          </p>
        ) : null}
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" className="min-h-11">
              Cancel
            </Button>
          </DialogClose>
          <Button className="min-h-11" onClick={confirm} disabled={apply.isPending || planChanged}>
            {apply.isPending ? "Applying" : "Apply changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ScenariosSkeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]" aria-busy="true">
      <Skeleton className="h-96" />
      <Skeleton className="h-96" />
      <span className="sr-only">Computing staffing scenarios</span>
    </div>
  );
}
