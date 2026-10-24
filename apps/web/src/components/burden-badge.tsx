import { STATUS_CLASS, STATUS_ICON, type Status } from "@/components/status";
import { cn } from "@/lib/utils";

export type BurdenCategory = "low" | "moderate" | "high" | "severe";

const BURDEN: Record<BurdenCategory, { status: Status; label: string }> = {
  low: { status: "good", label: "Low burden" },
  moderate: { status: "info", label: "Moderate burden" },
  high: { status: "warning", label: "High burden" },
  severe: { status: "critical", label: "Severe burden" },
};

/** Overtime burden category with its icon, label and model probability. */
export function BurdenBadge({
  category,
  probability,
  className,
}: {
  category: BurdenCategory;
  probability: number;
  className?: string;
}) {
  const { status, label } = BURDEN[category];
  const Icon = STATUS_ICON[status];
  return (
    <span
      className={cn(
        "inline-flex min-h-8 items-center gap-2 rounded-md border px-2.5 text-sm font-medium",
        STATUS_CLASS[status],
        className,
      )}
    >
      <Icon className="size-4" aria-hidden />
      <span>{label}</span>
      <span className="tabular border-s border-current/30 ps-2 font-normal">
        {Math.round(probability * 100)}%<span className="sr-only"> probability</span>
      </span>
    </span>
  );
}
