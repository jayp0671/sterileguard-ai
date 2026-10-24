import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { BurdenBadge } from "@/components/burden-badge";
import { ChartFrame } from "@/components/chart-frame";
import { DataTable, dataTableColumns, toCsv } from "@/components/data-table";
import { DriverList } from "@/components/driver-list";
import { MetricCard } from "@/components/metric-card";
import { StaffTimeline } from "@/components/staff-timeline";
import { EmptyState, ErrorState, PageHeader } from "@/components/states";
import { StatusPill } from "@/components/status";
import { renderWithProviders as render } from "@/test/render";

describe("MetricCard", () => {
  it("shows value, unit, 80% range and a delta whose direction drives the label", () => {
    render(
      <MetricCard
        label="Overtime"
        value={6.4}
        unit="h"
        range={[3.1, 9.25]}
        delta={-1.2}
        deltaLabel="vs last week"
      />,
    );
    const card = screen.getByRole("region", { name: "Overtime" });
    expect(within(card).getByText("6.4")).toBeInTheDocument();
    expect(within(card).getByText("3.1 to 9.3")).toBeInTheDocument();
    expect(within(card).getByText("−1.2").parentElement).toHaveClass("text-status-good");
  });

  it("marks an increase in overtime as bad", () => {
    render(<MetricCard label="OT" value={2} delta={0.5} />);
    expect(screen.getByText("+0.5").parentElement).toHaveClass("text-status-critical");
  });
});

describe("BurdenBadge and StatusPill", () => {
  it("never relies on color alone: label and probability are text", () => {
    render(<BurdenBadge category="high" probability={0.62} />);
    expect(screen.getByText("High burden")).toBeInTheDocument();
    expect(screen.getByText(/62%/)).toBeInTheDocument();
    expect(screen.getByText("probability")).toHaveClass("sr-only");
  });

  it("status pill carries a text label", () => {
    render(<StatusPill status="critical" label="Sterilizer down" />);
    expect(screen.getByText("Sterilizer down")).toBeInTheDocument();
  });
});

describe("DriverList", () => {
  it("prints signed hours and an accessible direction", () => {
    render(
      <DriverList
        drivers={[
          { sentence: "More patients than usual", hours: 2.1 },
          { sentence: "Both sterilizers working", hours: -0.8 },
        ]}
      />,
    );
    expect(screen.getByText("More patients than usual")).toBeInTheDocument();
    expect(screen.getByText(/\+2\.1 h/)).toBeInTheDocument();
    expect(screen.getByText(/−0\.8 h/)).toBeInTheDocument();
    expect(screen.getByText("less overtime")).toBeInTheDocument();
  });
});

describe("StaffTimeline", () => {
  it("describes every window, outside support and stayers for screen readers", () => {
    render(
      <StaffTimeline
        windows={[
          { label: "Morning", start: "07:00", end: "15:00", count: 3 },
          { label: "11:00", start: "11:00", end: "19:00", count: 3 },
        ]}
        outsideSupport={{ count: 2, start: "12:00", end: "20:00" }}
        willingToStay={2}
      />,
    );
    const caption = screen.getByText(/Staffing by shift window/);
    expect(caption).toHaveTextContent("Morning: 3 from 07:00 to 15:00.");
    expect(caption).toHaveTextContent("Outside support: 2 from 12:00 to 20:00.");
    expect(caption).toHaveTextContent("2 willing to stay for overtime.");
  });
});

describe("states", () => {
  it("EmptyState renders title, description and action", () => {
    render(
      <EmptyState
        title="No shifts yet"
        description="Log one to start"
        action={<button type="button">Log</button>}
      />,
    );
    expect(screen.getByRole("heading", { name: "No shifts yet" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log" })).toBeInTheDocument();
  });

  it("ErrorState copies the request id", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    const onRetry = vi.fn();
    render(<ErrorState detail="API unreachable" requestId="req-123" onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("req-123");
    await userEvent.click(screen.getByRole("button", { name: /copy id/i }));
    expect(writeText).toHaveBeenCalledWith("req-123");
    expect(await screen.findByRole("button", { name: /copied/i })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("PageHeader renders an h1 with eyebrow and actions", () => {
    render(
      <PageHeader
        title="Forecast"
        eyebrow="Tomorrow"
        actions={<button type="button">Run</button>}
      />,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Forecast" })).toBeInTheDocument();
    expect(screen.getByText("Tomorrow")).toBeInTheDocument();
  });
});

describe("ChartFrame", () => {
  it("toggles to an accessible table view", async () => {
    render(
      <ChartFrame
        title="Overtime by day"
        description="Predicted hours"
        columns={["Day", "Hours"]}
        rows={[
          ["Mon", 4.2],
          ["Tue", 6],
        ]}
      >
        <svg aria-label="chart" />
      </ChartFrame>,
    );
    expect(screen.getByLabelText("chart")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "View as table" }));
    const table = screen.getByRole("table", { name: "Overtime by day" });
    expect(within(table).getByText("4.2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View as chart" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});

type Row = { day: string; hours: number };
const col = dataTableColumns<Row>();
const columns = col.columns([
  col.accessor("day", { header: "Day" }),
  col.accessor("hours", { header: "Hours", meta: { numeric: true } }),
]);
const rows: Row[] = Array.from({ length: 25 }, (_, i) => ({
  day: `D${String(i).padStart(2, "0")}`,
  hours: i % 7,
}));

describe("DataTable", () => {
  it("paginates, filters, sorts and exports CSV", async () => {
    const onExport = vi.fn();
    render(
      <DataTable
        data={rows}
        columns={columns}
        caption="Shifts"
        pageSize={10}
        onExportCsv={onExport}
      />,
    );
    const table = screen.getByRole("table", { name: "Shifts" });
    expect(within(table).getAllByRole("row")).toHaveLength(11); // header + 10
    expect(screen.getByText(/25 rows · page 1 of 3/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText(/page 2 of 3/)).toBeInTheDocument();

    await userEvent.type(screen.getByRole("textbox", { name: "Filter rows" }), "D2");
    expect(screen.getByText(/5 rows/)).toBeInTheDocument(); // D20 to D24

    // Numbers sort descending first (TanStack default), then ascending.
    const header = () => screen.getByRole("columnheader", { name: /hours/i });
    await userEvent.click(screen.getByRole("button", { name: /hours/i }));
    expect(header()).toHaveAttribute("aria-sort", "descending");
    await userEvent.click(screen.getByRole("button", { name: /hours/i }));
    expect(header()).toHaveAttribute("aria-sort", "ascending");

    await userEvent.click(screen.getByRole("button", { name: /csv/i }));
    expect(onExport).toHaveBeenCalledOnce();
    expect(onExport.mock.calls[0]?.[0]).toMatch(/^Day,Hours\n/);
  });

  it("quotes CSV cells that need it", () => {
    expect(toCsv(["a", "b"], [["x,y", 'say "hi"']])).toBe('a,b\n"x,y","say ""hi"""');
  });
});
