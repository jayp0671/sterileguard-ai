"use client";

import { ApiError } from "@sg/contracts";
import {
  CheckCheck,
  CircleCheck,
  CircleX,
  Download,
  History,
  Minus,
  PencilLine,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ReauthDialog } from "@/components/auth/reauth-dialog";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { EmptyState, ErrorState, PageHeader } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  exportShiftsCsv,
  type ShiftFilters,
  type ShiftOut,
  type ShiftStatus,
  useShift,
  useShifts,
  useTransition,
} from "@/hooks/use-shifts";

const LEADS = ["supervisor", "dept_admin"];
const STATUS_LABEL: Record<ShiftStatus, string> = {
  draft: "Draft",
  submitted: "Submitted",
  approved: "Approved",
};
const ROLE_LABEL: Record<string, string> = {
  technician: "Technician",
  supervisor: "Supervisor",
  dept_admin: "Dept admin",
  data_steward: "Data steward",
  platform_admin: "Platform admin",
};
const h = (v: number | null | undefined) => (v === null || v === undefined ? "–" : v.toFixed(1));
const signed = (v: number | null | undefined) =>
  v === null || v === undefined ? "–" : `${v > 0 ? "+" : ""}${v.toFixed(1)}`;

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

type Row = ShiftOut & { select: string; actions: string };

export function ShiftHistory({ departmentId, roles }: { departmentId: string; roles: string[] }) {
  const isLead = roles.some((r) => LEADS.includes(r));
  const isAdmin = roles.includes("dept_admin");
  const router = useRouter();
  const params = useSearchParams();
  const [filters, setFilters] = useState<ShiftFilters>({ from: isoDaysAgo(60) });
  const shifts = useShifts(departmentId, filters);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmBulk, setConfirmBulk] = useState(false);
  const [reauth, setReauth] = useState(false);
  const open = params.get("shift");
  const setOpen = (id: string | null) =>
    router.replace(id ? `/app/history?shift=${id}` : "/app/history", { scroll: false });
  const transition = useTransition(departmentId);

  const data: Row[] = useMemo(
    () => (shifts.data ?? []).map((s) => ({ ...s, select: s.id, actions: s.id })),
    [shifts.data],
  );
  const approvable = data.filter((s) => s.status === "submitted");
  const toggle = (id: string) =>
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const columns = useMemo(() => {
    const col = dataTableColumns<Row>();
    return col.columns([
      ...(isLead
        ? [
            col.accessor("select", {
              header: "Select",
              enableSorting: false,
              cell: (c) =>
                c.row.original.status === "submitted" ? (
                  <input
                    type="checkbox"
                    className="size-5"
                    aria-label={`Select ${c.row.original.shift_date}`}
                    checked={selected.has(c.row.original.id)}
                    onChange={() => toggle(c.row.original.id)}
                  />
                ) : null,
            }),
          ]
        : []),
      col.accessor("shift_date", { header: "Date" }),
      col.accessor("ot_labor_hours", {
        header: "Overtime h",
        meta: { numeric: true },
        cell: (c) => h(c.getValue()),
      }),
      col.accessor((r) => r.forecast?.ot_p50 ?? null, {
        id: "predicted",
        header: "Predicted h",
        meta: { numeric: true },
        cell: (c) => h(c.getValue()),
      }),
      col.accessor("error", {
        header: "Error h",
        meta: { numeric: true },
        cell: (c) => signed(c.getValue()),
      }),
      col.accessor(
        (r) =>
          r.inside_range === null || r.inside_range === undefined
            ? ""
            : r.inside_range
              ? "yes"
              : "no",
        {
          id: "inside",
          header: "In range",
          cell: (c) => <RangeIcon inside={c.row.original.inside_range} />,
        },
      ),
      col.accessor("status", {
        header: "Status",
        cell: (c) => (
          <span className="inline-flex items-center gap-1.5">
            <Badge variant={c.getValue() === "approved" ? "default" : "secondary"}>
              {STATUS_LABEL[c.getValue()]}
            </Badge>
            {c.row.original.source === "simulated" ? (
              <span className="text-13 text-muted-foreground">Simulated</span>
            ) : null}
          </span>
        ),
      }),
      col.accessor((r) => ROLE_LABEL[r.author_role ?? ""] ?? "–", {
        id: "author",
        header: "Logged by",
      }),
      col.accessor("actions", {
        header: "Details",
        enableSorting: false,
        cell: (c) => (
          <Button
            variant="ghost"
            className="min-h-11"
            onClick={() => setOpen(c.row.original.id)}
            aria-label={`Details for ${c.row.original.shift_date}`}
          >
            Open
          </Button>
        ),
      }),
    ]);
  }, [isLead, selected]);

  async function approveSelected() {
    const ids = [...selected];
    const results = await Promise.allSettled(
      ids.map((id) => transition.mutateAsync({ id, action: "approve" })),
    );
    const ok = results.filter((r) => r.status === "fulfilled").length;
    setSelected(new Set());
    setConfirmBulk(false);
    if (ok === ids.length) toast.success(`${ok} shift${ok === 1 ? "" : "s"} approved`);
    else toast.error(`${ok} of ${ids.length} approved; the rest changed or were not submitted`);
  }

  async function download(token: string) {
    try {
      const from = filters.from ?? isoDaysAgo(60);
      const to = filters.to ?? new Date().toISOString().slice(0, 10);
      const blob = await exportShiftsCsv(departmentId, from, to, token);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `shift-actuals-${from}-${to}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err instanceof ApiError ? (err.detail ?? err.title) : "Export failed");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Shift history"
        title="Predicted vs actual"
        description="Each logged day with the forecast made for it: the error and whether the actual fell inside the 80% range."
        actions={
          <>
            <Button asChild className="min-h-11">
              <Link href="/app/log">
                <PencilLine aria-hidden /> Log a shift
              </Link>
            </Button>
            {isLead ? (
              <Button variant="outline" className="min-h-11" onClick={() => setReauth(true)}>
                <Download aria-hidden /> Export CSV
              </Button>
            ) : null}
          </>
        }
      />

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <Label htmlFor="f-status">Status</Label>
          <select
            id="f-status"
            className="h-11 rounded-md border bg-card px-3 text-sm"
            value={filters.status ?? ""}
            onChange={(e) =>
              setFilters((f) => ({ ...f, status: (e.target.value || undefined) as ShiftStatus }))
            }
          >
            <option value="">All</option>
            <option value="draft">Draft</option>
            <option value="submitted">Submitted</option>
            <option value="approved">Approved</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="f-from">From</Label>
          <Input
            id="f-from"
            type="date"
            className="h-11"
            value={filters.from ?? ""}
            onChange={(e) => setFilters((f) => ({ ...f, from: e.target.value || undefined }))}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="f-to">To</Label>
          <Input
            id="f-to"
            type="date"
            className="h-11"
            value={filters.to ?? ""}
            onChange={(e) => setFilters((f) => ({ ...f, to: e.target.value || undefined }))}
          />
        </div>
        {isLead ? (
          <Button
            className="ms-auto min-h-11"
            disabled={selected.size === 0}
            onClick={() => setConfirmBulk(true)}
          >
            <CheckCheck aria-hidden /> Approve selected ({selected.size})
          </Button>
        ) : null}
      </div>

      {shifts.isPending ? (
        <Skeleton className="h-96" aria-busy="true" />
      ) : shifts.isError ? (
        <ErrorState
          title="The shift history could not be loaded"
          detail={shifts.error instanceof ApiError ? shifts.error.detail : undefined}
          onRetry={() => void shifts.refetch()}
        />
      ) : data.length === 0 ? (
        <EmptyState
          icon={History}
          title="No shifts logged in this range"
          description="Log what happened after a shift to compare it with the forecast."
        />
      ) : (
        <DataTable data={data} columns={columns} caption="Shift history" pageSize={20} />
      )}
      {isLead && approvable.length > 0 && selected.size === 0 ? (
        <p className="text-13 text-muted-foreground">
          {approvable.length} submitted shift{approvable.length === 1 ? "" : "s"} waiting for
          approval.
        </p>
      ) : null}

      <Dialog open={confirmBulk} onOpenChange={setConfirmBulk}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Approve {selected.size} shift{selected.size === 1 ? "" : "s"}?
            </DialogTitle>
            <DialogDescription>
              Approved rows are locked. Only a department admin can reopen one, with a reason.
            </DialogDescription>
          </DialogHeader>
          <ul className="flex flex-col gap-1 text-sm">
            {data
              .filter((s) => selected.has(s.id))
              .map((s) => (
                <li key={s.id} className="tabular">
                  {s.shift_date}: {h(s.ot_labor_hours)} h
                </li>
              ))}
          </ul>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline" className="min-h-11">
                Cancel
              </Button>
            </DialogClose>
            <Button className="min-h-11" onClick={() => void approveSelected()}>
              Approve
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ReauthDialog
        open={reauth}
        onOpenChange={setReauth}
        action="export shift history"
        onVerified={(token) => void download(token)}
      />

      <ShiftDrawer
        departmentId={departmentId}
        id={open}
        onClose={() => setOpen(null)}
        isLead={isLead}
        isAdmin={isAdmin}
      />
    </div>
  );
}

function RangeIcon({ inside }: { inside: boolean | null | undefined }) {
  if (inside === null || inside === undefined)
    return (
      <span className="inline-flex items-center gap-1 text-muted-foreground">
        <Minus className="size-4" aria-hidden />
        <span className="sr-only">No forecast</span>
      </span>
    );
  return inside ? (
    <span className="inline-flex items-center gap-1 text-status-good">
      <CircleCheck className="size-4" aria-hidden /> Yes
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-status-warning">
      <CircleX className="size-4" aria-hidden /> No
    </span>
  );
}

function ShiftDrawer({
  departmentId,
  id,
  onClose,
  isLead,
  isAdmin,
}: {
  departmentId: string;
  id: string | null;
  onClose: () => void;
  isLead: boolean;
  isAdmin: boolean;
}) {
  const shift = useShift(departmentId, id);
  const transition = useTransition(departmentId);
  const [reason, setReason] = useState("");
  const s = shift.data;
  const act = (action: "submit" | "approve" | "reopen") =>
    transition.mutate(
      { id: id ?? "", action, reason },
      {
        onSuccess: () => {
          setReason("");
          toast.success(
            action === "reopen" ? "Reopened" : action === "approve" ? "Approved" : "Submitted",
          );
          void shift.refetch();
        },
      },
    );
  const fields: [string, string][] = s
    ? [
        ["Overtime", `${h(s.ot_labor_hours)} h`],
        [
          "Forecast",
          s.forecast
            ? `${h(s.forecast.ot_p50)} h (range ${h(s.forecast.ot_p10)} to ${h(s.forecast.ot_p90)})`
            : "None for this date",
        ],
        ["Error", s.error === null || s.error === undefined ? "–" : `${signed(s.error)} h`],
        ["Emergency and intake", String(s.emergency_intake_patients ?? "–")],
        ["Returned unused", String(s.returned_unused_estimate ?? "–")],
        ["Downtime", s.equipment_downtime_minutes ? `${s.equipment_downtime_minutes} min` : "–"],
        ["Status", STATUS_LABEL[s.status]],
        ["Logged by", ROLE_LABEL[s.author_role ?? ""] ?? "–"],
        ["Source", s.source === "real" ? "Real" : "Simulated"],
      ]
    : [];
  return (
    <Sheet open={Boolean(id)} onOpenChange={(o) => (o ? null : onClose())}>
      <SheetContent className="flex w-full flex-col gap-4 overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{s ? `Shift ${s.shift_date}` : "Shift"}</SheetTitle>
          <SheetDescription>Every field, and who changed what.</SheetDescription>
        </SheetHeader>
        {shift.isPending ? (
          <Skeleton className="h-64" />
        ) : s ? (
          <div className="flex flex-col gap-4 px-4 pb-6">
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
              {fields.map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd className="tabular">{v}</dd>
                </div>
              ))}
            </dl>
            {s.notes ? (
              <div>
                <p className="engraved">Notes</p>
                <p className="text-sm">{s.notes}</p>
              </div>
            ) : null}
            {s.reopen_reason ? (
              <p className="text-13 text-muted-foreground">Reopened: {s.reopen_reason}</p>
            ) : null}

            <div className="flex flex-wrap gap-2">
              {s.status === "draft" && (s.mine || isLead) ? (
                <Button className="min-h-11" onClick={() => act("submit")}>
                  Submit
                </Button>
              ) : null}
              {s.status === "submitted" && isLead ? (
                <Button className="min-h-11" onClick={() => act("approve")}>
                  Approve
                </Button>
              ) : null}
            </div>
            {s.status === "approved" && isAdmin ? (
              <div className="flex flex-col gap-2 border-t pt-3">
                <Label htmlFor="reopen-reason">Reason to reopen</Label>
                <Textarea
                  id="reopen-reason"
                  value={reason}
                  maxLength={500}
                  onChange={(e) => setReason(e.target.value)}
                />
                <Button
                  variant="outline"
                  className="min-h-11 self-start"
                  disabled={reason.trim().length < 3}
                  onClick={() => act("reopen")}
                >
                  Reopen
                </Button>
              </div>
            ) : null}
            {transition.isError ? (
              <p role="alert" className="text-sm text-destructive">
                {transition.error instanceof ApiError
                  ? (transition.error.detail ?? transition.error.title)
                  : "The change could not be saved."}
              </p>
            ) : null}

            {s.audit ? (
              <section
                aria-labelledby="audit-heading"
                className="flex flex-col gap-2 border-t pt-3"
              >
                <h3 id="audit-heading" className="engraved">
                  Audit trail
                </h3>
                <ol className="flex flex-col gap-2 text-13">
                  {s.audit.map((a) => (
                    <li key={`${a.occurred_at}-${a.action}`} className="rounded-md border p-2">
                      <p className="font-medium">
                        {a.action} · {new Date(a.occurred_at).toLocaleString("en-US")}
                      </p>
                      <ul className="text-muted-foreground">
                        {Object.entries(a.changes).map(([field, [from, to]]) => (
                          <li key={field}>
                            {field}: {String(from ?? "–")} to {String(to ?? "–")}
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ol>
              </section>
            ) : null}
          </div>
        ) : (
          <p className="px-4 text-sm text-muted-foreground">This shift could not be loaded.</p>
        )}
      </SheetContent>
    </Sheet>
  );
}
