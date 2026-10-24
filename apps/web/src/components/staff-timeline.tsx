import { Hand } from "lucide-react";
import { cn } from "@/lib/utils";

export type StaffWindow = { label: string; start: string; end: string; count: number };

const DAY_START = 7 * 60;
const DAY_END = 23 * 60;
const toMin = (hhmm: string) => {
  const [h = "0", m = "0"] = hhmm.split(":");
  return Number(h) * 60 + Number(m);
};
const pos = (hhmm: string) => ((toMin(hhmm) - DAY_START) / (DAY_END - DAY_START)) * 100;
const HOURS = ["07:00", "11:00", "13:00", "15:00", "19:00", "23:00"];

/**
 * Shift windows on a 07:00 to 23:00 scale: one track per window with its head count, the
 * outside support band, and a marker for morning staff willing to stay.
 */
export function StaffTimeline({
  windows,
  outsideSupport,
  willingToStay,
  className,
}: {
  windows: StaffWindow[];
  outsideSupport?: { count: number; start: string; end: string };
  willingToStay?: number;
  className?: string;
}) {
  const tracks = [
    ...windows.map((w) => ({ ...w, kind: "window" as const })),
    ...(outsideSupport
      ? [{ label: "Outside support", ...outsideSupport, kind: "support" as const }]
      : []),
  ];
  return (
    <figure className={cn("rounded-lg border bg-card p-4", className)}>
      <figcaption className="sr-only">
        {`Staffing by shift window. ${tracks
          .map((t) => `${t.label}: ${t.count} from ${t.start} to ${t.end}.`)
          .join(" ")}${
          willingToStay !== undefined ? ` ${willingToStay} willing to stay for overtime.` : ""
        }`}
      </figcaption>
      <div aria-hidden className="flex flex-col gap-2">
        <div className="relative ms-28 h-5 gauge-rail">
          {HOURS.map((h) => (
            <span
              key={h}
              className="tabular absolute -translate-x-1/2 text-xs text-muted-foreground"
              style={{ left: `${pos(h)}%` }}
            >
              {h}
            </span>
          ))}
        </div>
        {tracks.map((t) => (
          <div key={t.label} className="flex items-center gap-3">
            <span className="w-25 shrink-0 truncate text-13 text-muted-foreground">{t.label}</span>
            <div className="relative h-7 flex-1 rounded-sm bg-muted/60">
              <div
                className={cn(
                  "absolute inset-y-0 flex items-center rounded-sm px-2 text-13 font-medium",
                  t.kind === "support"
                    ? "border border-dashed border-input text-foreground"
                    : "bg-primary text-primary-foreground",
                )}
                style={{ left: `${pos(t.start)}%`, width: `${pos(t.end) - pos(t.start)}%` }}
              >
                <span className="tabular">{t.count}</span>
              </div>
              {t.kind === "window" && t.start === "07:00" && willingToStay !== undefined ? (
                <span
                  className="absolute -top-1 flex h-9 items-center gap-1 border-s-2 border-status-warning ps-1 text-xs text-status-warning"
                  style={{ left: `${pos(t.end)}%` }}
                >
                  <Hand className="size-3.5" />
                  <span className="tabular">{willingToStay} stay</span>
                </span>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </figure>
  );
}
