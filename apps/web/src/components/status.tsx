import { AlertOctagon, AlertTriangle, CheckCircle2, Info, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export type Status = "good" | "warning" | "critical" | "info";

export const STATUS_ICON: Record<Status, LucideIcon> = {
  good: CheckCircle2,
  warning: AlertTriangle,
  critical: AlertOctagon,
  info: Info,
};

export const STATUS_CLASS: Record<Status, string> = {
  good: "bg-status-good-bg text-status-good border-status-good-border",
  warning: "bg-status-warning-bg text-status-warning border-status-warning-border",
  critical: "bg-status-critical-bg text-status-critical border-status-critical-border",
  info: "bg-status-info-bg text-status-info border-status-info-border",
};

/** Status is never color alone: always an icon plus a text label. */
export function StatusPill({
  status,
  label,
  className,
}: {
  status: Status;
  label: string;
  className?: string;
}) {
  const Icon = STATUS_ICON[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-13 font-medium",
        STATUS_CLASS[status],
        className,
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      {label}
    </span>
  );
}
