"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartFrame } from "@/components/chart-frame";
import type { HistoryPoint } from "@/hooks/use-forecast";

const short = (iso: string) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });

const h = (v: number | null | undefined) => (v === null || v === undefined ? "" : v.toFixed(1));

/** "In the last 14 days, actual overtime fell inside the range on 11 of 13 days." */
export function coverageSummary(points: HistoryPoint[], days: number): string {
  const logged = points.filter((p) => p.actual !== null && p.actual !== undefined);
  if (logged.length === 0) {
    return `No actual overtime has been logged for the last ${days} days yet.`;
  }
  const inside = logged.filter(
    (p) => (p.actual as number) >= p.ot_p10 && (p.actual as number) <= p.ot_p90,
  ).length;
  const noun = logged.length === 1 ? "day" : "days";
  return `In the last ${days} days, actual overtime fell inside the range on ${inside} of ${logged.length} ${noun}.`;
}

/** Predicted band (p10 to p90), the most likely line and actual dots, with a table view. */
export function HistoryChart({ points, days = 14 }: { points: HistoryPoint[]; days?: number }) {
  const data = points.map((p) => ({
    label: short(p.date),
    band: [p.ot_p10, p.ot_p90] as [number, number],
    p50: p.ot_p50,
    actual: p.actual ?? undefined,
  }));
  const summary = coverageSummary(points, days);
  return (
    <ChartFrame
      title={`Predicted vs actual, last ${days} days`}
      description={summary}
      columns={["Date", "Low (p10)", "Most likely", "High (p90)", "Actual"]}
      rows={points.map((p) => [p.date, h(p.ot_p10), h(p.ot_p50), h(p.ot_p90), h(p.actual)])}
    >
      <div className="h-64 w-full" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 12, fill: "var(--muted-foreground)" }}
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
            />
            <YAxis
              tick={{ fontSize: 12, fill: "var(--muted-foreground)" }}
              tickLine={false}
              axisLine={false}
              unit=" h"
            />
            <Tooltip
              contentStyle={{
                background: "var(--popover)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                fontSize: 13,
              }}
              formatter={(value, name) => {
                if (Array.isArray(value)) return [`${h(value[0])} to ${h(value[1])} h`, "Range"];
                return [`${h(value as number)} h`, name === "p50" ? "Most likely" : "Actual"];
              }}
            />
            <Area
              dataKey="band"
              stroke="none"
              fill="var(--chart-1)"
              fillOpacity={0.18}
              isAnimationActive={false}
            />
            <Line
              dataKey="p50"
              stroke="var(--chart-1)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Scatter dataKey="actual" fill="var(--chart-5)" isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}
