"use client";

import { ApiError } from "@sg/contracts";
import { CalendarClock, Cpu, FlaskConical, PencilLine, RefreshCw } from "lucide-react";
import Link from "next/link";
import { BurdenBadge } from "@/components/burden-badge";
import { ForecastDrivers } from "@/components/forecast/forecast-drivers";
import { HistoryChart } from "@/components/forecast/history-chart";
import { MetricCard } from "@/components/metric-card";
import { StaffTimeline } from "@/components/staff-timeline";
import { EmptyState, ErrorState, PageHeader } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  type ForecastOut,
  useComputeForecast,
  useForecastHistory,
  useNextDayForecast,
} from "@/hooks/use-forecast";
import { type PlanOut, usePlan } from "@/hooks/use-plan";
import { nextWorkday } from "@/lib/plan-fields";

export const EDITORS = ["supervisor", "dept_admin"];
const HISTORY_DAYS = 14;

const fmt = (v: number) => v.toFixed(1);

export function longDate(iso: string): string {
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}

/** Staffing windows of the plan on the 07:00 to 23:00 timeline. */
function timeline(values: PlanOut["values"]) {
  const n = (v: unknown) => (typeof v === "number" ? v : 0);
  return {
    windows: [
      { label: "7:00 AM", start: "07:00", end: "15:00", count: n(values.morning_staff_present) },
      { label: "11:00 AM", start: "11:00", end: "19:00", count: n(values.aft_11_staff) },
      { label: "1:00 PM", start: "13:00", end: "21:00", count: n(values.aft_13_staff) },
      { label: "3:00 PM", start: "15:00", end: "23:00", count: n(values.aft_15_staff) },
    ],
    outsideSupport: { count: n(values.outside_support_staff), start: "12:00", end: "20:00" },
    willingToStay: n(values.ot_available_staff),
  };
}

function problem(err: unknown): { detail?: string; requestId?: string } {
  if (err instanceof ApiError) return { detail: err.detail ?? err.title, requestId: err.requestId };
  return { detail: err instanceof Error ? err.message : undefined };
}

export function ForecastHome({
  departmentId,
  roles,
  date = nextWorkday(),
}: {
  departmentId: string | undefined;
  roles: string[];
  date?: string;
}) {
  const canCompute = roles.some((r) => EDITORS.includes(r));
  const plan = usePlan(departmentId, date);
  const forecast = useNextDayForecast(departmentId);
  const history = useForecastHistory(departmentId, HISTORY_DAYS);
  const compute = useComputeForecast();
  const run = () => departmentId && compute.mutate({ departmentId, date });

  const f = forecast.data;
  const loading = plan.isPending || forecast.isPending;
  const noPlan = plan.data?.suggested === true;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Forecast"
        title={`Tomorrow, ${longDate(date)}`}
        description="Overtime of the morning operation, from the plan known before 7:00 AM."
        actions={
          <>
            {f ? (
              <span className="inline-flex min-h-11 items-center gap-1.5 rounded-md border px-2.5 text-13 text-muted-foreground">
                <Cpu className="size-4" aria-hidden />
                Model <span className="tabular text-foreground">{f.model_version}</span>
              </span>
            ) : null}
            {canCompute && f ? (
              <Button
                variant="outline"
                className="min-h-11"
                onClick={run}
                disabled={compute.isPending}
              >
                <RefreshCw className={compute.isPending ? "animate-spin" : undefined} aria-hidden />
                {compute.isPending ? "Recomputing" : "Recompute"}
              </Button>
            ) : null}
            <Button asChild variant="ghost" className="min-h-11">
              <Link href="/app/plan">
                <PencilLine aria-hidden />
                {canCompute ? "Edit plan" : "View plan"}
              </Link>
            </Button>
            <Tooltip>
              <TooltipTrigger asChild>
                <span tabIndex={0} className="inline-flex">
                  <Button variant="ghost" className="min-h-11" disabled>
                    <FlaskConical aria-hidden />
                    Try staffing scenarios
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent>Staffing scenarios arrive in the next release.</TooltipContent>
            </Tooltip>
          </>
        }
      />

      {compute.isError ? (
        <ErrorState
          title={
            compute.error instanceof ApiError && compute.error.status === 503
              ? "The forecast model is not loaded"
              : "The forecast could not be computed"
          }
          {...problem(compute.error)}
          onRetry={run}
        />
      ) : null}

      {loading ? (
        <ForecastSkeleton />
      ) : forecast.isError ? (
        <ErrorState
          title="The forecast could not be loaded"
          {...problem(forecast.error)}
          onRetry={() => void forecast.refetch()}
        />
      ) : f ? (
        <ForecastBody
          forecast={f}
          plan={plan.data}
          stale={Boolean(
            plan.data?.updated_at && f.created_at && plan.data.updated_at > f.created_at,
          )}
        />
      ) : noPlan ? (
        <EmptyState
          icon={CalendarClock}
          title="No plan for tomorrow yet"
          description="The forecast is computed from tomorrow's plan: patients, staff by start time and equipment."
          action={
            <Button asChild className="min-h-11">
              <Link href="/app/plan">{canCompute ? "Plan tomorrow" : "View tomorrow's plan"}</Link>
            </Button>
          }
        />
      ) : (
        <EmptyState
          icon={Cpu}
          title="Tomorrow's plan is saved"
          description={
            canCompute
              ? "Compute the forecast to see the estimate, its range and what drives it."
              : "A supervisor has not computed the forecast yet."
          }
          action={
            canCompute ? (
              <Button className="min-h-11" onClick={run} disabled={compute.isPending}>
                {compute.isPending ? "Computing" : "Compute forecast"}
              </Button>
            ) : undefined
          }
        />
      )}

      {history.data && history.data.length > 0 ? (
        <HistoryChart points={history.data} days={HISTORY_DAYS} />
      ) : null}
    </div>
  );
}

function ForecastBody({
  forecast: f,
  plan,
  stale,
}: {
  forecast: ForecastOut;
  plan: PlanOut | undefined;
  stale: boolean;
}) {
  const probability = f.burden_probs[f.burden_class] ?? 0;
  const provisional = f.thresholds.source.includes("provisional");
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <div className="flex flex-col gap-4">
        <MetricCard
          label="Overtime estimate"
          value={f.ot_p50}
          unit="overtime hours"
          range={[f.ot_p10, f.ot_p90]}
          size="hero"
          footer={
            <div className="flex flex-col gap-3 border-t pt-3">
              <p className="text-sm">
                Most likely <span className="tabular font-medium">{fmt(f.ot_p50)}</span>, range{" "}
                <span className="tabular font-medium">{fmt(f.ot_p10)}</span> to{" "}
                <span className="tabular font-medium">{fmt(f.ot_p90)}</span> (80%)
              </p>
              <BurdenBadge category={f.burden_class} probability={probability} />
              {provisional ? (
                <p className="text-13 text-muted-foreground">
                  Categories are provisional until enough real data is collected.
                </p>
              ) : null}
              {stale ? (
                <p className="text-13 text-status-warning">
                  The plan changed after this forecast. Recompute to update it.
                </p>
              ) : null}
              <p className="engraved">{f.disclaimer}</p>
            </div>
          }
        />
        {plan && !plan.suggested ? (
          <section aria-labelledby="staffing-heading" className="flex flex-col gap-2">
            <h2 id="staffing-heading" className="engraved">
              Planned staffing
            </h2>
            <StaffTimeline {...timeline(plan.values)} />
          </section>
        ) : null}
      </div>
      <ForecastDrivers drivers={f.drivers ?? []} />
    </div>
  );
}

function ForecastSkeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]" aria-busy="true">
      <Skeleton className="h-72" />
      <Skeleton className="h-72" />
      <span className="sr-only">Loading the forecast</span>
    </div>
  );
}
