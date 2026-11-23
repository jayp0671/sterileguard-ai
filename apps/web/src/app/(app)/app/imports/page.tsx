"use client";

import { Suspense } from "react";
import { useDepartment } from "@/components/shell/department-context";
import { EmptyState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { ImportsView } from "./imports-view";

/** Imports (SG-24): data stewards and department admins. */
export default function ImportsPage() {
  const { departmentId, roles, me } = useDepartment();
  if (!me || !departmentId) return <Skeleton className="h-96" aria-busy="true" />;
  if (!roles.some((r) => r === "data_steward" || r === "dept_admin")) {
    return (
      <EmptyState
        title="Imports are for data stewards"
        description="Ask a department admin if you need to load a file."
      />
    );
  }
  return (
    <Suspense fallback={<Skeleton className="h-96" aria-busy="true" />}>
      <ImportsView departmentId={departmentId} roles={roles} />
    </Suspense>
  );
}
