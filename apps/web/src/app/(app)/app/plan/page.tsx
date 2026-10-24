"use client";

import { useDepartment } from "@/components/shell/department-context";
import { Skeleton } from "@/components/ui/skeleton";
import { PlanForm } from "./plan-form";

const EDITORS = ["supervisor", "dept_admin"];

/** Plan tomorrow (supervisors, dept admins) or Tomorrow's plan, read only (technicians). */
export default function PlanPage() {
  const { departmentId, roles, me } = useDepartment();
  if (!me) return <Skeleton className="h-96" aria-busy="true" />;
  return <PlanForm departmentId={departmentId} canEdit={roles.some((r) => EDITORS.includes(r))} />;
}
