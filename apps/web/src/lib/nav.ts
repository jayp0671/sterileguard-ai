import type { components } from "@sg/contracts";
import {
  Activity,
  Bell,
  Building2,
  CalendarCheck,
  ClipboardList,
  Cog,
  Database,
  FileClock,
  FlaskConical,
  Gauge,
  History,
  type LucideIcon,
  Palette,
  ShieldCheck,
  Upload,
  Users,
} from "lucide-react";

export type AppRole = components["schemas"]["Membership"]["roles"][number];

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Roles that see the item. Empty means every member. */
  roles: AppRole[];
  /** Label shown instead when the user only has read access. */
  readOnlyLabel?: { roles: AppRole[]; label: string };
  devOnly?: boolean;
};

export type NavSection = { label: string; items: NavItem[] };

const LEADS: AppRole[] = ["supervisor", "dept_admin"];
const ADMINS: AppRole[] = ["dept_admin", "platform_admin"];

/** Sitemap from plan §2.4. Items appear only for roles that can use them. */
export const NAV: NavSection[] = [
  {
    label: "Operate",
    items: [
      { href: "/app", label: "Forecast", icon: Gauge, roles: [] },
      {
        href: "/app/plan",
        label: "Plan tomorrow",
        icon: CalendarCheck,
        roles: [...LEADS, "technician"],
        readOnlyLabel: { roles: ["technician"], label: "Tomorrow's plan" },
      },
      { href: "/app/scenarios", label: "Scenarios", icon: FlaskConical, roles: LEADS },
      {
        href: "/app/log",
        label: "Log a shift",
        icon: ClipboardList,
        roles: ["technician", ...LEADS],
      },
      { href: "/app/history", label: "Shift history", icon: History, roles: [] },
    ],
  },
  {
    label: "Data",
    items: [
      {
        href: "/app/imports",
        label: "Imports",
        icon: Upload,
        roles: ["data_steward", "dept_admin"],
      },
      {
        href: "/app/model",
        label: "Model performance",
        icon: Activity,
        roles: [...LEADS, "data_steward"],
      },
      { href: "/app/notifications", label: "Notifications", icon: Bell, roles: [] },
    ],
  },
  {
    label: "Admin",
    items: [
      { href: "/app/admin/users", label: "Users and invites", icon: Users, roles: ADMINS },
      { href: "/app/admin/department", label: "Department settings", icon: Cog, roles: ADMINS },
      { href: "/app/admin/audit", label: "Audit log", icon: FileClock, roles: ADMINS },
      { href: "/app/admin/retention", label: "Data retention", icon: Database, roles: ADMINS },
    ],
  },
  {
    label: "Platform",
    items: [
      {
        href: "/app/platform/orgs",
        label: "Organizations",
        icon: Building2,
        roles: ["platform_admin"],
      },
      {
        href: "/app/platform/models",
        label: "Model registry",
        icon: ShieldCheck,
        roles: ["platform_admin"],
      },
    ],
  },
  {
    label: "You",
    items: [
      { href: "/app/settings", label: "Settings", icon: Cog, roles: [] },
      { href: "/app/style", label: "Style", icon: Palette, roles: [], devOnly: true },
    ],
  },
];

/** Sections and items visible to someone holding `roles` in the current department. */
export function navFor(
  roles: AppRole[],
  { showDevOnly = false }: { showDevOnly?: boolean } = {},
): NavSection[] {
  const has = (need: AppRole[]) => need.length === 0 || need.some((r) => roles.includes(r));
  return NAV.map((section) => ({
    label: section.label,
    items: section.items
      .filter((item) => has(item.roles) && (showDevOnly || !item.devOnly))
      .map((item) => {
        const ro = item.readOnlyLabel;
        const onlyReadOnly =
          ro &&
          roles.some((r) => ro.roles.includes(r)) &&
          !roles.some((r) => !ro.roles.includes(r));
        return onlyReadOnly ? { ...item, label: ro.label } : item;
      }),
  })).filter((section) => section.items.length > 0);
}
