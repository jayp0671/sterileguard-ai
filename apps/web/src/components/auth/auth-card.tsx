import { OctagonAlert } from "lucide-react";
import type { ReactNode } from "react";
import { BrandMark, Wordmark } from "@/components/brand";

/**
 * Shared frame for the public auth pages: a steel brand panel (hidden on small screens) and
 * the form. Tablet friendly: the form column is at least 44px per control and centered.
 */
export function AuthCard({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <main className="grid min-h-dvh lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-steel-950 p-10 text-steel-100 lg:flex">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 h-40 opacity-60 gauge-rail [--gauge-tick:rgb(179_190_198/18%)]"
        />
        <Wordmark className="text-teal-300 [&>span:last-child]:text-steel-50" />
        <div className="flex max-w-md flex-col gap-4">
          <BrandMark className="size-12 text-teal-400" />
          <p className="text-2xl font-medium leading-tight text-steel-50">
            Tomorrow&apos;s overtime, estimated the evening before.
          </p>
          <p className="text-sm text-steel-300">
            Decision support for Dental Central Sterile. Model estimates, not guarantees.
          </p>
        </div>
        <p className="engraved text-steel-400">Academic prototype · HIPAA-style safeguards</p>
      </aside>
      <div className="flex flex-col justify-center px-4 py-12 sm:px-10">
        <div className="mx-auto flex w-full max-w-sm flex-col gap-6">
          <Wordmark className="lg:hidden" />
          <header className="flex flex-col gap-1.5">
            <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
            {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
          </header>
          <div className="flex flex-col gap-4 [&_button]:min-h-11 [&_input]:min-h-11">
            {children}
          </div>
        </div>
      </div>
    </main>
  );
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p
      role="alert"
      className="flex items-start gap-2 rounded-md border border-status-critical-border bg-status-critical-bg px-3 py-2 text-sm text-status-critical"
    >
      <OctagonAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span>{message}</span>
    </p>
  );
}
