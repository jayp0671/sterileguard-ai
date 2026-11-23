"use client";

import { useDepartment } from "@/components/shell/department-context";
import { EmptyState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { ModelPerformance } from "./model-performance";

const READERS = ["supervisor", "dept_admin", "data_steward", "platform_admin"];

/** Model performance (SG-24): supervisors and above, and data stewards. */
export default function ModelPage() {
  const { departmentId, roles, me } = useDepartment();
  if (!me || !departmentId) return <Skeleton className="h-96" aria-busy="true" />;
  if (!roles.some((r) => READERS.includes(r))) {
    return <EmptyState title="Model performance is for supervisors" />;
  }
  return <ModelPerformance departmentId={departmentId} />;
}
