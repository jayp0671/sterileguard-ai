import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

const fmt = (v: number, digits: number) =>
  v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });

/**
 * The hero number: engraved label, large tabular value, unit, an 80% range drawn as a scale,
 * and an optional signed delta. `deltaGoodWhen` says which direction is good, so color and
 * icon agree (overtime going down is good).
 */
export function MetricCard({
  label,
  value,
  unit,
  digits = 1,
  range,
  rangeLabel = "80% range",
  scaleMax,
  delta,
  deltaLabel,
  deltaGoodWhen = "down",
  footer,
  size = "md",
  className,
}: {
  label: string;
  value: number;
  unit?: string;
  digits?: number;
  range?: [number, number];
  rangeLabel?: string;
  /** Upper end of the range scale; defaults to 1.5 x the range's upper bound. */
  scaleMax?: number;
  delta?: number;
  deltaLabel?: string;
  deltaGoodWhen?: "up" | "down";
  footer?: ReactNode;
  /** "hero" is the page's main readout: a large Plex Mono numeral. */
  size?: "md" | "hero";
  className?: string;
}) {
  const max = scaleMax ?? Math.max((range?.[1] ?? value) * 1.5, 1);
  const pct = (v: number) => `${Math.min(100, Math.max(0, (v / max) * 100))}%`;
  const deltaGood =
    delta === undefined || delta === 0 ? null : delta < 0 === (deltaGoodWhen === "down");
  const DeltaIcon =
    delta === undefined || delta === 0 ? Minus : delta > 0 ? ArrowUpRight : ArrowDownRight;

  return (
    <section
      aria-label={label}
      className={cn("flex flex-col gap-3 rounded-lg border bg-card p-4 sm:p-5", className)}
    >
      <h3 className="engraved">{label}</h3>
      <p className="flex items-baseline gap-2">
        <span
          className={cn(
            "tabular font-medium leading-none tracking-tight",
            size === "hero" ? "font-mono text-5xl sm:text-6xl" : "text-3xl",
          )}
        >
          {fmt(value, digits)}
        </span>
        {unit ? <span className="text-sm text-muted-foreground">{unit}</span> : null}
      </p>
      {range ? (
        <div className="flex flex-col gap-1.5">
          <div className="relative h-2 rounded-full bg-muted gauge-rail" aria-hidden>
            <div
              className="absolute inset-y-0 rounded-full bg-primary/25"
              style={{ left: pct(range[0]), width: `calc(${pct(range[1])} - ${pct(range[0])})` }}
            />
            <div
              className="absolute -top-1 h-4 w-0.5 rounded-full bg-primary"
              style={{ left: pct(value) }}
            />
          </div>
          <p className="text-13 text-muted-foreground">
            {rangeLabel}{" "}
            <span className="tabular text-foreground">
              {fmt(range[0], digits)} to {fmt(range[1], digits)}
            </span>
            {unit ? ` ${unit}` : null}
          </p>
        </div>
      ) : null}
      {delta !== undefined ? (
        <p
          className={cn(
            "inline-flex items-center gap-1 text-13",
            deltaGood === null
              ? "text-muted-foreground"
              : deltaGood
                ? "text-status-good"
                : "text-status-critical",
          )}
        >
          <DeltaIcon className="size-4" aria-hidden />
          <span className="tabular">
            {delta > 0 ? "+" : delta < 0 ? "−" : "±"}
            {fmt(Math.abs(delta), digits)}
          </span>
          {deltaLabel ? <span className="text-muted-foreground">{deltaLabel}</span> : null}
        </p>
      ) : null}
      {footer}
    </section>
  );
}
