"use client";

import { useDepartment } from "@/components/shell/department-context";
import { Skeleton } from "@/components/ui/skeleton";
import { ScenariosView } from "./scenarios-view";

/** Staffing scenarios (SG-19). Data is fetched client-side, like the Forecast home. */
export default function ScenariosPage() {
  const { departmentId, roles, me } = useDepartment();
  if (!me) return <Skeleton className="h-96" aria-busy="true" />;
  return <ScenariosView departmentId={departmentId} roles={roles} />;
}
