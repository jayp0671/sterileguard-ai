"use client";

import { Check, Copy, Inbox, type LucideIcon, OctagonAlert } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-3 rounded-lg border border-dashed px-6 py-10 text-center",
        className,
      )}
    >
      <Icon className="size-8 text-muted-foreground" aria-hidden />
      <h3 className="text-base font-medium">{title}</h3>
      {description ? <p className="max-w-sm text-sm text-muted-foreground">{description}</p> : null}
      {action}
    </div>
  );
}

/** A problem+json failure: what happened, what to try, and the request id to quote. */
export function ErrorState({
  title = "Something went wrong",
  detail,
  requestId,
  onRetry,
  className,
}: {
  title?: string;
  detail?: string;
  requestId?: string;
  onRetry?: () => void;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    if (!requestId) return;
    await navigator.clipboard.writeText(requestId);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col gap-3 rounded-lg border border-status-critical-border bg-status-critical-bg p-4 text-status-critical",
        className,
      )}
    >
      <p className="flex items-center gap-2 font-medium">
        <OctagonAlert className="size-5" aria-hidden />
        {title}
      </p>
      {detail ? <p className="text-sm text-foreground">{detail}</p> : null}
      <div className="flex flex-wrap items-center gap-2">
        {requestId ? (
          <>
            <span className="text-13 text-foreground">
              Request ID <code className="tabular">{requestId}</code>
            </span>
            <Button variant="outline" size="sm" className="min-h-11" onClick={copy}>
              {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
              {copied ? "Copied" : "Copy ID"}
            </Button>
          </>
        ) : null}
        {onRetry ? (
          <Button variant="outline" size="sm" className="min-h-11" onClick={onRetry}>
            Try again
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function PageHeader({
  title,
  eyebrow,
  description,
  actions,
  className,
}: {
  title: string;
  eyebrow?: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        "flex flex-col gap-3 border-b pb-4 gauge-rail sm:flex-row sm:items-end sm:justify-between",
        className,
      )}
    >
      <div className="flex flex-col gap-1">
        {eyebrow ? <p className="engraved">{eyebrow}</p> : null}
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description ? (
          <p className="max-w-prose text-sm text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </header>
  );
}
