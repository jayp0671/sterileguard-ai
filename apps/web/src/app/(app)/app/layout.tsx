import type { ReactNode } from "react";
import { IdleTimeoutGuard } from "@/components/auth/idle-timeout-guard";
import { AppShell } from "@/components/shell/app-shell";

/** Everything under /app requires an aal2 session (enforced by src/proxy.ts and RLS). */
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <IdleTimeoutGuard />
      <AppShell>{children}</AppShell>
    </>
  );
}
