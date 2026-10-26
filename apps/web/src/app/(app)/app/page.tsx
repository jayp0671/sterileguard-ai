"use client";

import { useDepartment } from "@/components/shell/department-context";
import { Skeleton } from "@/components/ui/skeleton";
import { ForecastHome } from "./forecast-home";

/**
 * Forecast home (SG-15). The department is chosen in the shell (remembered per browser), so the
 * data is fetched client-side with React Query; skeletons hold the layout while it loads.
 */
export default function AppHome() {
  const { departmentId, roles, me } = useDepartment();
  if (!me) return <Skeleton className="h-96" aria-busy="true" />;
  return <ForecastHome departmentId={departmentId} roles={roles} />;
}
