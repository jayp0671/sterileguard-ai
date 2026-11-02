"use client";

import {
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { ChartFrame } from "@/components/chart-frame";
import type { OptionOut, ScenarioOut } from "@/hooks/use-scenarios";
import { changeSummary, chartPoints, hours } from "@/lib/scenarios";

type Point = ReturnType<typeof chartPoints>[number];

const SERIES = [
  { kind: "other", label: "Option", fill: "var(--chart-2)", size: 40 },
  { kind: "pareto", label: "Best trade-off", fill: "var(--chart-1)", size: 60 },
  { kind: "low", label: "Low confidence", fill: "var(--chart-4)", size: 40 },
  { kind: "minimum", label: "Recommended minimum", fill: "var(--chart-5)", size: 140 },
] as const;

function Legend() {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-13 text-muted-foreground">
      {SERIES.map((s) => (
        <li key={s.kind} className="inline-flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-block size-2.5 rounded-full"
            style={{ background: s.fill, opacity: s.kind === "low" ? 0.7 : 1 }}
          />
          {s.label}
        </li>
      ))}
      <li className="inline-flex items-center gap-1.5">
        <span
          aria-hidden
          className="inline-block size-2.5 rounded-full border-2 border-foreground"
        />
        Shown above
      </li>
    </ul>
  );
}

/** Added staff-hours against predicted overtime for every option with the chosen number of
 * volunteers: the recommended minimum highlighted, low-confidence options greyed. */
export function TradeoffChart({
  scenario,
  volunteers,
  selected,
  onSelect,
}: {
  scenario: ScenarioOut;
  volunteers: number;
  selected: OptionOut | undefined;
  onSelect: (option: OptionOut) => void;
}) {
  const points = chartPoints(scenario, volunteers);
  const target = scenario.target.type === "p50_hours" ? scenario.target.value : undefined;
  const sorted = [...points].sort((a, b) => a.x - b.x || a.y - b.y);
  return (
    <ChartFrame
      title="Trade-off: staff added vs predicted overtime"
      description={`Each dot is one staffing option with ${volunteers} staff willing to stay. Lower and further left is better. Select a dot to show it.`}
      columns={[
        "Change",
        "Added staff-hours",
        "Most likely (h)",
        "Range (h)",
        "Meets target",
        "Note",
      ]}
      rows={sorted.map((p) => [
        changeSummary(p.option),
        p.x,
        p.y,
        `${hours(p.option.ot_p10)} to ${hours(p.option.ot_p90)}`,
        p.option.meets_target ? "Yes" : "No",
        p.kind === "minimum"
          ? "Recommended minimum"
          : p.kind === "low"
            ? "Low confidence"
            : p.kind === "pareto"
              ? "Best trade-off"
              : "",
      ])}
    >
      <Legend />
      <div className="h-72 w-full" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 8, right: 12, bottom: 8, left: -8 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" />
            <XAxis
              type="number"
              dataKey="x"
              name="Added staff-hours"
              unit=" h"
              tick={{ fontSize: 12, fill: "var(--muted-foreground)" }}
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
            />
            <YAxis
              type="number"
              dataKey="y"
              name="Most likely overtime"
              unit=" h"
              tick={{ fontSize: 12, fill: "var(--muted-foreground)" }}
              tickLine={false}
              axisLine={false}
            />
            <ZAxis type="number" dataKey="z" range={[40, 140]} />
            {target !== undefined ? (
              <ReferenceLine
                y={target}
                stroke="var(--chart-5)"
                strokeDasharray="4 4"
                label={{
                  value: `Target ${hours(target)} h`,
                  position: "insideTopRight",
                  fontSize: 12,
                  fill: "var(--muted-foreground)",
                }}
              />
            ) : null}
            <Tooltip
              cursor={{ strokeDasharray: "2 4" }}
              contentStyle={{
                background: "var(--popover)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                fontSize: 13,
              }}
              formatter={(value, name) => [`${hours(Number(value))} h`, name]}
              labelFormatter={() => ""}
            />
            {SERIES.map((s) => (
              <Scatter
                key={s.kind}
                name={s.label}
                data={points.filter((p) => p.kind === s.kind).map((p) => ({ ...p, z: s.size }))}
                fill={s.fill}
                fillOpacity={s.kind === "low" ? 0.6 : 1}
                isAnimationActive={false}
                onClick={(d: { payload?: Point }) => d.payload && onSelect(d.payload.option)}
                cursor="pointer"
              />
            ))}
            {selected ? (
              <Scatter
                name="Shown above"
                data={[{ x: selected.added_staff_hours, y: selected.ot_p50, z: 140 }]}
                fill="transparent"
                stroke="var(--foreground)"
                strokeWidth={2}
                isAnimationActive={false}
              />
            ) : null}
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}
