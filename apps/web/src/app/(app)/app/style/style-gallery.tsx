"use client";

import { Bell } from "lucide-react";
import type { ReactNode } from "react";
import { BrandMark, Wordmark } from "@/components/brand";
import { BurdenBadge } from "@/components/burden-badge";
import { ChartFrame } from "@/components/chart-frame";
import { DataTable, dataTableColumns } from "@/components/data-table";
import { DriverList } from "@/components/driver-list";
import { MetricCard } from "@/components/metric-card";
import { StaffTimeline } from "@/components/staff-timeline";
import { EmptyState, ErrorState, PageHeader } from "@/components/states";
import { StatusPill } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const SCALES = ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"];
const SEMANTIC = [
  "background",
  "foreground",
  "card",
  "primary",
  "muted",
  "muted-foreground",
  "accent",
  "destructive",
  "border",
  "input",
  "ring",
];
const TYPE = [
  ["text-xs", "12"],
  ["text-13", "13"],
  ["text-sm", "14"],
  ["text-base", "16"],
  ["text-lg", "20"],
  ["text-xl", "24"],
  ["text-2xl", "32"],
  ["text-3xl", "40"],
];

type Shift = { date: string; patients: number; ot: number };
const col = dataTableColumns<Shift>();
const shiftColumns = col.columns([
  col.accessor("date", { header: "Date" }),
  col.accessor("patients", { header: "Patients", meta: { numeric: true } }),
  col.accessor("ot", { header: "Overtime h", meta: { numeric: true } }),
]);
// Synthetic sample rows for the gallery only.
const shifts: Shift[] = Array.from({ length: 12 }, (_, i) => ({
  date: `2026-10-${String(5 + i).padStart(2, "0")}`,
  patients: 280 + ((i * 37) % 160),
  ot: Math.round((((i * 53) % 110) / 10) * 10) / 10,
}));

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="engraved">{title}</h2>
      {children}
    </section>
  );
}

function Gallery() {
  return (
    <div className="flex flex-col gap-10 bg-background p-6 text-foreground">
      <Section title="Brand">
        <div className="flex items-center gap-6">
          <Wordmark />
          <BrandMark className="size-10 text-primary" title="SterileGuard mark" />
        </div>
      </Section>
      <Section title="Color scales">
        {(["steel", "teal"] as const).map((scale) => (
          <div key={scale} className="grid grid-cols-11 gap-1">
            {SCALES.map((step) => (
              <div key={step} className="flex flex-col gap-1">
                <div
                  className="h-10 rounded-sm border"
                  style={{ background: `var(--${scale}-${step})` }}
                />
                <span className="tabular text-xs text-muted-foreground">
                  {scale} {step}
                </span>
              </div>
            ))}
          </div>
        ))}
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
          {SEMANTIC.map((name) => (
            <div key={name} className="flex items-center gap-2">
              <span className="size-6 rounded-sm border" style={{ background: `var(--${name})` }} />
              <span className="text-13">{name}</span>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusPill status="good" label="Good" />
          <StatusPill status="warning" label="Warning" />
          <StatusPill status="critical" label="Critical" />
          <StatusPill status="info" label="Info" />
        </div>
      </Section>
      <Section title="Type">
        {TYPE.map(([cls, px]) => (
          <p key={cls} className={cls}>
            <span className="tabular me-3 text-xs text-muted-foreground">{px}px</span>
            Sterile processing overtime <span className="tabular">1,234.5 h</span>
          </p>
        ))}
      </Section>
      <Section title="Controls">
        <div className="flex flex-wrap items-center gap-2">
          <Button className="h-11">Primary</Button>
          <Button variant="outline" className="h-11">
            Outline
          </Button>
          <Button variant="ghost" className="h-11">
            Ghost
          </Button>
          <Button variant="destructive" className="h-11">
            Destructive
          </Button>
          <Input aria-label="Example input" placeholder="Input" className="h-11 max-w-xs" />
        </div>
      </Section>
      <Section title="Page header">
        <PageHeader
          eyebrow="Tomorrow · Tue Oct 27"
          title="Forecast"
          description="Model estimate, not a guarantee."
          actions={<Button className="h-11">Run forecast</Button>}
        />
      </Section>
      <Section title="Metrics">
        <div className="grid gap-3 sm:grid-cols-3">
          <MetricCard
            label="Predicted overtime"
            value={7.4}
            unit="h"
            range={[4.1, 11.2]}
            delta={-1.3}
            deltaLabel="vs plan"
          />
          <MetricCard label="Regular patients" value={392} digits={0} />
          <MetricCard label="Backlog at 7:00" value={1} digits={0} unit="normal" delta={0} />
        </div>
        <div className="flex flex-wrap gap-2">
          <BurdenBadge category="low" probability={0.71} />
          <BurdenBadge category="moderate" probability={0.48} />
          <BurdenBadge category="high" probability={0.62} />
          <BurdenBadge category="severe" probability={0.33} />
        </div>
      </Section>
      <Section title="Drivers">
        <DriverList
          drivers={[
            { sentence: "More regular patients than a usual Wednesday", hours: 2.4 },
            { sentence: "One sterilizer is down", hours: 1.6 },
            { sentence: "An extra staff member starts at 11:00", hours: -1.1 },
          ]}
        />
      </Section>
      <Section title="Staff timeline">
        <StaffTimeline
          windows={[
            { label: "Morning", start: "07:00", end: "15:00", count: 3 },
            { label: "11:00 start", start: "11:00", end: "19:00", count: 3 },
            { label: "13:00 start", start: "13:00", end: "21:00", count: 1 },
            { label: "15:00 start", start: "15:00", end: "23:00", count: 2 },
          ]}
          outsideSupport={{ count: 2, start: "12:00", end: "20:00" }}
          willingToStay={2}
        />
      </Section>
      <Section title="Chart frame">
        <ChartFrame
          title="Overtime by day"
          description="Synthetic sample of predicted overtime hours."
          columns={["Date", "Overtime h"]}
          rows={shifts.slice(0, 5).map((s) => [s.date, s.ot])}
        >
          <div className="flex h-32 items-end gap-2" aria-hidden>
            {shifts.slice(0, 5).map((s) => (
              <div
                key={s.date}
                className="flex-1 rounded-t-sm bg-primary"
                style={{ height: `${(s.ot / 12) * 100}%` }}
              />
            ))}
          </div>
        </ChartFrame>
      </Section>
      <Section title="Data table">
        <DataTable data={shifts} columns={shiftColumns} caption="Sample shifts" pageSize={5} />
      </Section>
      <Section title="States">
        <div className="grid gap-3 sm:grid-cols-2">
          <EmptyState
            icon={Bell}
            title="No notifications"
            description="Alerts about tomorrow's plan show up here."
          />
          <ErrorState
            title="Forecast failed"
            detail="The API returned an error."
            requestId="req-7f3a9c"
            onRetry={() => undefined}
          />
        </div>
      </Section>
    </div>
  );
}

export function StyleGallery() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Dev and staging only"
        title="Style"
        description="Every token and component in light and dark. Visual regression baseline (SG-31)."
      />
      <div className="grid gap-6 2xl:grid-cols-2">
        <div className="light overflow-hidden rounded-lg border" data-theme-sample="light">
          <Gallery />
        </div>
        <div className="dark overflow-hidden rounded-lg border" data-theme-sample="dark">
          <Gallery />
        </div>
      </div>
    </div>
  );
}
