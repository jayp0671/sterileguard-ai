"use client";

import { useDepartment } from "@/components/shell/department-context";
import { Skeleton } from "@/components/ui/skeleton";
import { ShiftForm } from "./shift-form";

/** Log a shift (SG-20): a 4-step form for a tablet, with drafts kept on the device and server. */
export default function LogShiftPage() {
  const { departmentId, roles, me } = useDepartment();
  if (!me || !departmentId) return <Skeleton className="h-96" aria-busy="true" />;
  return <ShiftForm key={departmentId} departmentId={departmentId} roles={roles} />;
}
