import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ModelCardView, Performance } from "@/hooks/use-performance";
import { Providers } from "@/test/render";
import { PerformanceBody } from "./model-performance";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const model: ModelCardView = {
  version: "20261026-0105-de605a9",
  feature_set: "full",
  status: "active",
  gates_passed: true,
  created_at: "2026-10-26T00:00:00Z",
  activated_at: "2026-10-26T01:05:00Z",
  activated_by_role: "cli",
  datasets: ["a76064e0-2f6f-5317-a0f1-e5a322718464"],
  thresholds: [5.67, 12.13],
  thresholds_source: "simulated_provisional",
  holdout: { mae: 0.82, rmse: 1.96, coverage_80: 0.812, mean_width_80: 2.67 },
  feature_sets: {
    full: { mae: 0.82, rmse: 1.96, coverage_80: 0.812, mean_width_80: 2.67 },
    core: { mae: 6.8, rmse: 8.06, coverage_80: 0.903, mean_width_80: 21.66 },
  },
  baselines: { baseline_ridge: 1.91 },
  shap_global: [{ feature: "ot_available_staff", mean_abs_shap: 6.2 }],
  card: {
    intended_use: "Decision support only. Model estimate, not a guarantee.",
    limitations: ["Trained on simulated days."],
    features: ["regular_patients"],
    run_id: "20261026-002617-full-s42",
    trained_at: null,
    gates: [{ name: "interval_coverage", passed: true, required: true, message: "ok" }],
  },
};

const empty: Performance = {
  department_id: "d",
  active: [model],
  registry: null,
  live: {
    window_days: 30,
    days: 0,
    coverage_target: 0.8,
    daily: [],
    residual_histogram: [],
    confusion: null,
  },
};

const withReal: Performance = {
  ...empty,
  live: {
    window_days: 30,
    days: 2,
    mae: 1.25,
    rmse: 1.46,
    coverage_80: 0.5,
    coverage_target: 0.8,
    bias: 1.25,
    daily: [
      {
        date: "2026-11-02",
        p10: 5,
        p50: 6,
        p90: 7,
        actual: 6.5,
        error: 0.5,
        covered: true,
        predicted_class: "moderate",
      },
      {
        date: "2026-11-03",
        p10: 7,
        p50: 8,
        p90: 9,
        actual: 10,
        error: 2,
        covered: false,
        predicted_class: "moderate",
      },
    ],
    residual_histogram: [{ start: 0.5, end: 2, count: 2 }],
    confusion: null,
  },
};

function show(data: Performance) {
  return render(
    <Providers>
      <PerformanceBody data={data} window={30} onWindow={() => {}} />
    </Providers>,
  );
}

describe("PerformanceBody", () => {
  it("shows the empty state with a link to Log a shift before real actuals exist", () => {
    show(empty);
    expect(
      screen.getByText("Real-world accuracy appears after approved shift logs exist."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Log a shift" })).toHaveAttribute("href", "/app/log");
    expect(screen.getByText("Provisional (simulated)")).toBeInTheDocument();
    expect(screen.getByText("Simulated holdout: 0.82 h")).toBeInTheDocument();
  });

  it("shows live metrics and every chart has a table alternative", () => {
    show(withReal);
    expect(screen.getByText("1.25 h", { selector: "dd" })).toBeInTheDocument();
    expect(
      screen.getAllByText(/covered 1 of 2 real days \(50%\); target 80%/).length,
    ).toBeGreaterThan(0);
    const toggles = screen.getAllByRole("button", { name: /view as table/i });
    expect(toggles.length).toBe(3); // predicted vs actual, errors, SHAP
    fireEvent.click(toggles[0] as HTMLElement);
    const table = screen.getAllByRole("table")[0] as HTMLElement;
    expect(within(table).getByText("2026-11-03")).toBeInTheDocument();
  });

  it("renders the model card and the full vs core comparison", () => {
    show(empty);
    expect(
      screen.getByText("Decision support only. Model estimate, not a guarantee."),
    ).toBeInTheDocument();
    expect(screen.getByText("6.80")).toBeInTheDocument();
  });

  it("shows the registry with activate and rollback only for platform admins", () => {
    show({ ...empty, registry: [model, { ...model, version: "v-old", status: "retired" }] });
    expect(screen.getByRole("button", { name: "Roll back" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Activate" })).toBeInTheDocument();
  });
});
