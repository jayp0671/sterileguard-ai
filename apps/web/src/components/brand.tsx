import { cn } from "@/lib/utils";

/** Monoline mark: a shield with a check. Uses currentColor so it follows the theme. */
export function BrandMark({ className, title }: { className?: string; title?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn("size-6", className)}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
    >
      {title ? <title>{title}</title> : null}
      <path d="M12 2.75 19.5 5.6v5.5c0 4.5-3.1 8-7.5 9.5-4.4-1.5-7.5-5-7.5-9.5V5.6L12 2.75Z" />
      <path d="m8.6 11.8 2.4 2.4 4.5-4.8" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 text-primary", className)}>
      <BrandMark />
      <span className="font-semibold tracking-tight text-foreground">SterileGuard</span>
    </span>
  );
}
