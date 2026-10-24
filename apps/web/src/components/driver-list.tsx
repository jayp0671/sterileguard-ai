import { cn } from "@/lib/utils";

export type Driver = { sentence: string; hours: number };

/**
 * SHAP drivers in plain language. Each row has a sentence and a signed bar around a center
 * axis: right adds overtime, left removes it. The value is printed too, so the bar never
 * carries the meaning alone.
 */
export function DriverList({ drivers, className }: { drivers: Driver[]; className?: string }) {
  const max = Math.max(0.1, ...drivers.map((d) => Math.abs(d.hours)));
  return (
    <ul className={cn("flex flex-col divide-y rounded-lg border bg-card", className)}>
      {drivers.map((d) => {
        const up = d.hours >= 0;
        return (
          <li
            key={d.sentence}
            className="grid grid-cols-1 gap-2 px-4 py-3 sm:grid-cols-[1fr_12rem_4.5rem] sm:items-center"
          >
            <span className="text-sm">{d.sentence}</span>
            <span className="relative h-2 rounded-full bg-muted" aria-hidden>
              <span className="absolute -inset-y-1 left-1/2 w-px bg-border" />
              <span
                className={cn(
                  "absolute inset-y-0 rounded-full",
                  up ? "left-1/2 bg-status-warning" : "right-1/2 bg-primary",
                )}
                style={{ width: `${(Math.abs(d.hours) / max) * 50}%` }}
              />
            </span>
            <span className="tabular text-end text-sm">
              {up ? "+" : "−"}
              {Math.abs(d.hours).toFixed(1)} h
              <span className="sr-only">{up ? " more overtime" : " less overtime"}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
