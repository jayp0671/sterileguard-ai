"use client";

import { Suspense } from "react";
import { useDepartment } from "@/components/shell/department-context";
import { Skeleton } from "@/components/ui/skeleton";
import { ShiftHistory } from "./shift-history";

/** Shift history (SG-20): predicted vs actual per day, approvals and the detail drawer. */
export default function ShiftHistoryPage() {
  const { departmentId, roles, me } = useDepartment();
  if (!me || !departmentId) return <Skeleton className="h-96" aria-busy="true" />;
  return (
    <Suspense fallback={<Skeleton className="h-96" aria-busy="true" />}>
      <ShiftHistory departmentId={departmentId} roles={roles} />
    </Suspense>
  );
}
