import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { MetricCard } from "@/components/metric-card";
import type { DriverOut, HistoryPoint } from "@/hooks/use-forecast";
import messages from "@/messages/en.json";
import { ForecastDrivers } from "./forecast-drivers";
import { coverageSummary, HistoryChart } from "./history-chart";

const intl = ({ children }: { children: ReactNode }) => (
  <NextIntlClientProvider locale="en" messages={messages}>
    {children}
  </NextIntlClientProvider>
);

const driver = (over: Partial<DriverOut>): DriverOut => ({
  rank: 1,
  feature: "sterilizers_up",
  value: "1",
  contribution_hours: 1.24,
  text_key: "drivers.sterilizers_up.pos",
  text_params: { value: 1, hours: 1.2 },
  default_text: "Only 1 sterilizer available is adding about 1.2 hours",
  ...over,
});

describe("MetricCard hero", () => {
  it("formats the estimate and the 80% range to one decimal", () => {
    render(
      <MetricCard
        label="Overtime estimate"
        value={8}
        unit="overtime hours"
        range={[6.04, 11.5]}
        size="hero"
      />,
    );
    expect(screen.getByText("8.0")).toHaveClass("font-mono");
    expect(screen.getByText("6.0 to 11.5")).toBeInTheDocument();
  });
});

describe("ForecastDrivers", () => {
  it("translates sentences with ICU plurals and shows signed hours with icons", () => {
    render(
      <ForecastDrivers
        drivers={[
          driver({}),
          driver({
            rank: 2,
            feature: "aft_11_staff",
            value: "3",
            contribution_hours: -2.04,
            text_key: "drivers.aft_11_staff.neg",
            text_params: { value: 3, hours: 2 },
          }),
          driver({
            rank: 3,
            feature: "other",
            value: null,
            contribution_hours: 0.3,
            text_key: "drivers.other.pos",
            text_params: { hours: 0.3 },
          }),
        ]}
      />,
      { wrapper: intl },
    );
    expect(
      screen.getByText("Only 1 sterilizer available is adding about 1.2 hours"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("3 staff starting at 11:00 is reducing overtime by about 2 hours"),
    ).toBeInTheDocument();
    expect(screen.getByText(/\+1\.2 h/)).toHaveClass("text-status-warning");
    expect(screen.getByText(/−2\.0 h/)).toHaveClass("text-status-good");
    expect(screen.getByText("Other factors is adding about 0.3 hours")).toBeInTheDocument();
  });

  it("falls back to the default English sentence for an unknown key", () => {
    render(
      <ForecastDrivers
        drivers={[driver({ text_key: "drivers.new_feature.pos", default_text: "New thing" })]}
      />,
      { wrapper: intl },
    );
    expect(screen.getByText("New thing")).toBeInTheDocument();
  });

  it("opens the explanation drawer", () => {
    render(<ForecastDrivers drivers={[driver({})]} />, { wrapper: intl });
    fireEvent.click(screen.getByRole("button", { name: "Why these factors?" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("add up to the estimate exactly");
  });
});

const points: HistoryPoint[] = [
  { date: "2026-10-20", ot_p10: 4, ot_p50: 6, ot_p90: 8, actual: 7, model_version: "v1" },
  { date: "2026-10-21", ot_p10: 4, ot_p50: 6, ot_p90: 8, actual: 9.5, model_version: "v1" },
  { date: "2026-10-22", ot_p10: 1, ot_p50: 2, ot_p90: 3, actual: null, model_version: "v1" },
];

describe("HistoryChart", () => {
  it("summarises coverage for screen readers", () => {
    expect(coverageSummary(points, 14)).toBe(
      "In the last 14 days, actual overtime fell inside the range on 1 of 2 days.",
    );
    expect(coverageSummary([], 14)).toMatch(/No actual overtime/);
  });

  it("toggles to a table with one row per day", () => {
    render(<HistoryChart points={points} />);
    fireEvent.click(screen.getByRole("button", { name: "View as table" }));
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(4);
    expect(rows[2]).toHaveTextContent("2026-10-214.06.08.09.5");
    expect(screen.getByRole("button", { name: "View as chart" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
