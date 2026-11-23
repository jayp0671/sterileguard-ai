"use client";

import { SettingsAdmin } from "@/components/admin/admin-views";
import { useDepartment } from "@/components/shell/department-context";
import { EmptyState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";

/** Admin console (SG-25): dept admins; platform admins for every department. */
export default function Page() {
  const { departmentId, roles, me } = useDepartment();
  if (!me || !departmentId) return <Skeleton className="h-96" aria-busy="true" />;
  if (!roles.some((r) => r === "dept_admin" || r === "platform_admin")) {
    return <EmptyState title="This page is for department admins" />;
  }
  return <SettingsAdmin departmentId={departmentId} />;
}
