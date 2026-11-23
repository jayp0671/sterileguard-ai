"use client";

import { ApiError } from "@sg/contracts";
import { Activity, ClipboardList } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { toast } from "sonner";
import { ReauthDialog } from "@/components/auth/reauth-dialog";
import { ChartFrame } from "@/components/chart-frame";
import { EmptyState, ErrorState, PageHeader } from "@/components/states";
import { StatusPill } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  coverageText,
  type LiveMetrics,
  type ModelCardView,
  type Performance,
  usePerformance,
  useRegistryAction,
} from "@/hooks/use-performance";
import { cn } from "@/lib/utils";

const h = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined ? "—" : v.toFixed(digits);
const pct = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`;
const day = (iso: string) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
const AXIS = { fontSize: 12, fill: "var(--muted-foreground)" };
const TIP = {
  background: "var(--popover)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  fontSize: 13,
};

/** Model performance (SG-24 Part B, plan §12.7). */
export function ModelPerformance({ departmentId }: { departmentId: string }) {
  const [window, setWindow] = useState(30);
  const q = usePerformance(departmentId, window);
  if (q.isPending) return <Skeleton className="h-96" aria-busy="true" />;
  if (q.isError)
    return <ErrorState title="Performance could not be loaded" onRetry={() => q.refetch()} />;
  return <PerformanceBody data={q.data} window={window} onWindow={setWindow} />;
}

export function PerformanceBody({
  data,
  window,
  onWindow,
}: {
  data: Performance;
  window: number;
  onWindow: (w: number) => void;
}) {
  const model = data.active.find((m) => m.feature_set === "full") ?? data.active[0];
  const live = data.live;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Data"
        title="Model performance"
        description="How close the forecasts have been. Simulated holdout numbers come from training; real-world numbers use approved shift logs."
        actions={
          <label className="flex items-center gap-2 text-sm">
            Window
            <select
              className="min-h-11 rounded-md border bg-background px-2"
              value={window}
              onChange={(e) => onWindow(Number(e.target.value))}
            >
              {[14, 30, 60, 90].map((w) => (
                <option key={w} value={w}>
                  Last {w} days
                </option>
              ))}
            </select>
          </label>
        }
      />
      {model ? <VersionCard model={model} /> : null}
      <section aria-labelledby="tiles" className="flex flex-col gap-3">
        <h2 id="tiles" className="engraved">
          Real-world accuracy
        </h2>
        <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Tile
            label="Mean absolute error"
            value={`${h(live.mae)} h`}
            sim={`${h(model?.holdout.mae)} h`}
          />
          <Tile
            label="80% range coverage"
            value={pct(live.coverage_80)}
            sim={pct(model?.holdout.coverage_80)}
          />
          <Tile
            label="Bias (actual − most likely)"
            value={
              live.bias === null || live.bias === undefined
                ? "—"
                : `${live.bias > 0 ? "+" : ""}${h(live.bias)} h`
            }
            sim="0 by construction"
          />
          <Tile
            label="Real days scored"
            value={String(live.days)}
            sim={`window ${live.window_days} days`}
          />
        </dl>
      </section>
      {live.days === 0 ? (
        <EmptyState
          icon={ClipboardList}
          title="No real-world results yet"
          description="Real-world accuracy appears after approved shift logs exist."
          action={
            <Button asChild className="min-h-11">
              <Link href="/app/log">Log a shift</Link>
            </Button>
          }
        />
      ) : (
        <LiveCharts live={live} />
      )}
      {model ? <ModelDetails model={model} /> : null}
      {data.registry ? <Registry registry={data.registry} /> : null}
    </div>
  );
}

function Tile({ label, value, sim }: { label: string; value: string; sim: string }) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <dt className="engraved">{label}</dt>
      <dd className="mt-1 font-mono text-2xl tabular-nums">{value}</dd>
      <dd className="text-13 text-muted-foreground">Simulated holdout: {sim}</dd>
    </div>
  );
}

function VersionCard({ model }: { model: ModelCardView }) {
  const provisional = model.thresholds_source !== "real";
  return (
    <section
      aria-label="Active model"
      className="grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-5"
    >
      <Field label="Version" value={model.version} mono />
      <Field
        label="Activated"
        value={
          model.activated_at
            ? `${new Date(model.activated_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })} by ${
                model.activated_by_role === "platform_admin" ? "platform admin" : "sg CLI"
              }`
            : "—"
        }
      />
      <Field label="Feature set" value={model.feature_set} />
      <Field
        label="Training datasets"
        value={model.datasets.map((d) => d.slice(0, 8)).join(", ") || "—"}
        mono
      />
      <div>
        <p className="engraved">Burden thresholds</p>
        <StatusPill
          className="mt-1"
          status={provisional ? "warning" : "good"}
          label={provisional ? "Provisional (simulated)" : "Real data"}
        />
      </div>
    </section>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="engraved">{label}</p>
      <p className={cn("mt-1 break-all", mono && "font-mono text-13")}>{value}</p>
    </div>
  );
}

export function LiveCharts({ live }: { live: LiveMetrics }) {
  const points = live.daily.map((d) => ({ ...d, label: day(d.date), band: [d.p10, d.p90] }));
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <ChartFrame
        title="Predicted vs actual (real days)"
        description={coverageText(live)}
        columns={["Date", "Low (p10)", "Most likely", "High (p90)", "Actual", "Inside range"]}
        rows={live.daily.map((d) => [
          d.date,
          h(d.p10),
          h(d.p50),
          h(d.p90),
          h(d.actual),
          d.covered ? "yes" : "no",
        ])}
      >
        <div className="h-64" aria-hidden>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="label" tick={AXIS} tickLine={false} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} unit=" h" />
              <Tooltip contentStyle={TIP} />
              <Area
                dataKey="band"
                stroke="none"
                fill="var(--chart-1)"
                fillOpacity={0.18}
                name="80% range"
              />
              <Scatter dataKey="actual" fill="var(--foreground)" name="Actual" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </ChartFrame>
      <ChartFrame
        title="Errors (actual − most likely)"
        description={`Positive errors mean the day ran longer than forecast. Mean ${h(live.bias)} h.`}
        columns={["From (h)", "To (h)", "Days"]}
        rows={live.residual_histogram.map((b) => [h(b.start), h(b.end), b.count])}
      >
        <div className="h-64" aria-hidden>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={live.residual_histogram.map((b) => ({ ...b, label: h(b.start, 1) }))}
              margin={{ top: 8, right: 8, bottom: 0, left: -16 }}
            >
              <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="label" tick={AXIS} tickLine={false} unit=" h" />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip contentStyle={TIP} />
              <Bar dataKey="count" fill="var(--chart-2)" name="Days" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </ChartFrame>
      <section aria-labelledby="coverage" className="rounded-lg border bg-card p-4 lg:col-span-2">
        <h3 id="coverage" className="engraved">
          Interval coverage vs the 80% target
        </h3>
        <div className="relative mt-3 h-3 rounded-full bg-muted" aria-hidden>
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-primary"
            style={{ width: `${Math.round((live.coverage_80 ?? 0) * 100)}%` }}
          />
          <div className="absolute inset-y-[-4px] w-0.5 bg-foreground" style={{ left: "80%" }} />
        </div>
        <p className="mt-2 text-sm">{coverageText(live)}</p>
      </section>
      {live.confusion ? (
        <section
          aria-labelledby="confusion"
          className="rounded-lg border bg-card p-4 lg:col-span-2"
        >
          <h3 id="confusion" className="engraved">
            Burden category: actual (rows) vs predicted (columns)
          </h3>
          <Table>
            <TableCaption className="sr-only">Burden confusion matrix on real days</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>Actual</TableHead>
                {live.confusion.labels.map((l) => (
                  <TableHead key={l} className="text-right capitalize">
                    {l}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {live.confusion.matrix.map((row, i) => (
                <TableRow key={live.confusion?.labels[i]}>
                  <TableCell className="capitalize">{live.confusion?.labels[i]}</TableCell>
                  {row.map((n, j) => (
                    <TableCell
                      key={live.confusion?.labels[j]}
                      className="text-right font-mono tabular-nums"
                    >
                      {n}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>
      ) : null}
    </div>
  );
}

function ModelDetails({ model }: { model: ModelCardView }) {
  const shap = model.shap_global.map((s) => ({
    feature: s.feature.replaceAll("_", " "),
    value: s.mean_abs_shap ?? 0,
  }));
  const sets = Object.entries(model.feature_sets);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <ChartFrame
        title="What the model leans on (global SHAP)"
        description="Average size of each input's effect on the forecast, in hours, on simulated holdout days."
        columns={["Input", "Mean |SHAP| (h)"]}
        rows={shap.map((s) => [s.feature, h(s.value)])}
      >
        <div className="h-72" aria-hidden>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={shap}
              layout="vertical"
              margin={{ top: 0, right: 8, bottom: 0, left: 40 }}
            >
              <XAxis type="number" tick={AXIS} unit=" h" />
              <YAxis type="category" dataKey="feature" tick={AXIS} width={120} />
              <Tooltip contentStyle={TIP} />
              <Bar dataKey="value" fill="var(--chart-1)" name="Mean |SHAP|" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </ChartFrame>
      <section aria-labelledby="sets" className="rounded-lg border bg-card p-4">
        <h3 id="sets" className="engraved">
          Full vs core feature set (simulated holdout)
        </h3>
        <Table>
          <TableCaption className="sr-only">Holdout metrics by feature set</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>Feature set</TableHead>
              <TableHead className="text-right">MAE (h)</TableHead>
              <TableHead className="text-right">RMSE (h)</TableHead>
              <TableHead className="text-right">80% coverage</TableHead>
              <TableHead className="text-right">Range width (h)</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sets.map(([name, m]) => (
              <TableRow key={name}>
                <TableCell className="capitalize">{name}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{h(m.mae)}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{h(m.rmse)}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {pct(m.coverage_80)}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {h(m.mean_width_80)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
      <section
        aria-labelledby="card"
        className="flex flex-col gap-3 rounded-lg border bg-card p-4 lg:col-span-2"
      >
        <h3 id="card" className="text-base font-semibold">
          Model card
        </h3>
        <div>
          <p className="engraved">Intended use</p>
          <p className="mt-1 max-w-prose text-sm">{model.card.intended_use}</p>
        </div>
        <div>
          <p className="engraved">Limitations</p>
          <ul className="mt-1 list-disc pl-5 text-sm">
            {model.card.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </div>
        <div>
          <p className="engraved">Data</p>
          <p className="mt-1 text-sm">
            Run {model.card.run_id ?? "—"}, {model.card.features.length} features known by 7:00 AM,
            trained on simulated days ({model.datasets.length} dataset).
          </p>
        </div>
        <div>
          <p className="engraved">Activation gates</p>
          <ul className="mt-1 flex flex-col gap-1 text-sm">
            {model.card.gates.map((g) => (
              <li key={g.name} className="flex flex-wrap items-center gap-2">
                <StatusPill
                  status={g.passed ? "good" : g.required ? "critical" : "info"}
                  label={g.passed ? "Passed" : g.required ? "Failed" : "Not measured"}
                />
                <span className="font-mono text-13">{g.name}</span>
                <span className="text-muted-foreground">{g.message}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}

export function Registry({ registry }: { registry: ModelCardView[] }) {
  const action = useRegistryAction();
  const [pending, setPending] = useState<{
    action: "activate" | "rollback";
    model: ModelCardView;
  } | null>(null);
  return (
    <section aria-labelledby="registry" className="flex flex-col gap-3">
      <h2 id="registry" className="engraved">
        Model registry (platform admin)
      </h2>
      <Table>
        <TableCaption className="sr-only">Every registered model version</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>Version</TableHead>
            <TableHead>Feature set</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Gates</TableHead>
            <TableHead className="text-right">Holdout MAE</TableHead>
            <TableHead>Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {registry.map((m) => (
            <TableRow key={m.version}>
              <TableCell className="font-mono text-13">{m.version}</TableCell>
              <TableCell>{m.feature_set}</TableCell>
              <TableCell className="capitalize">{m.status}</TableCell>
              <TableCell>
                <StatusPill
                  status={m.gates_passed ? "good" : "warning"}
                  label={m.gates_passed ? "Passed" : "Not passed"}
                />
              </TableCell>
              <TableCell className="text-right font-mono tabular-nums">
                {h(m.holdout.mae)}
              </TableCell>
              <TableCell className="flex gap-2">
                {m.status !== "active" ? (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!m.gates_passed}
                    onClick={() => setPending({ action: "activate", model: m })}
                  >
                    Activate
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setPending({ action: "rollback", model: m })}
                  >
                    Roll back
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <ReauthDialog
        open={pending !== null}
        onOpenChange={(o) => !o && setPending(null)}
        action={
          pending?.action === "rollback" ? "roll back the active model" : "activate this model"
        }
        onVerified={async (freshToken) => {
          if (!pending) return;
          try {
            const out = await action.mutateAsync({
              action: pending.action,
              version: pending.model.version,
              featureSet: pending.model.feature_set,
              freshToken,
            });
            toast.success(`Active model is now ${out?.version ?? pending.model.version}`);
          } catch (err) {
            toast.error(err instanceof ApiError ? (err.detail ?? err.title) : "The change failed");
          } finally {
            setPending(null);
          }
        }}
      />
      <p className="flex items-center gap-2 text-13 text-muted-foreground">
        <Activity className="size-4" aria-hidden /> Every activation and rollback is recorded in the
        audit log.
      </p>
    </section>
  );
}
