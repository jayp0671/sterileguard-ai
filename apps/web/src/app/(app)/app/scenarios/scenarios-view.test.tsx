import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { API, server } from "@/test/msw";
import { Providers } from "@/test/render";
import { ScenariosView } from "./scenarios-view";

const DEPT = "00000000-0000-4000-8000-000000000003";
const DATE = "2026-11-03";
const BASE = {
  morning_staff_present: 3,
  aft_11_staff: 2,
  aft_13_staff: 1,
  outside_support_staff: 1,
  ot_available_staff: 2,
};
type Key = keyof typeof BASE;
const HOURS: Record<Key, number> = {
  morning_staff_present: 8,
  aft_11_staff: 4,
  aft_13_staff: 2,
  outside_support_staff: 8,
  ot_available_staff: 0,
};

/** A small synthetic grid: +0/+1 at 7:00 and 11:00, volunteers 1 or 2. */
function option(values: Record<Key, number>) {
  const changes = Object.fromEntries(
    Object.entries(values).map(([k, v]) => [k, v - BASE[k as Key]]),
  ) as Record<Key, number>;
  const added = (["morning_staff_present", "aft_11_staff"] as const).reduce(
    (s, k) => s + Math.max(0, changes[k]) * HOURS[k],
    0,
  );
  const p50 = 12 - changes.morning_staff_present * 3 - changes.aft_11_staff * 2.5;
  return {
    id: `m${changes.morning_staff_present}.a${changes.aft_11_staff}.v${values.ot_available_staff}`,
    values,
    changes,
    ot_p10: p50 - 2,
    ot_p50: p50,
    ot_p90: p50 + 3,
    burden_probs:
      p50 > 10 ? { low: 0.1, moderate: 0.3, high: 0.6 } : { low: 0.3, moderate: 0.6, high: 0.1 },
    added_staff_hours: added,
    meets_target: p50 <= 10,
    low_confidence: changes.morning_staff_present === 1 && changes.aft_11_staff === 1,
    what_if: values.ot_available_staff !== BASE.ot_available_staff,
  };
}

const options = [0, 1].flatMap((m) =>
  [0, 1].flatMap((a) =>
    [1, 2].map((v) =>
      option({
        ...BASE,
        morning_staff_present: 3 + m,
        aft_11_staff: 2 + a,
        ot_available_staff: v,
      }),
    ),
  ),
);
const base = options.find((o) => o.id === "m0.a0.v2");
const scenario = {
  id: "s-1",
  department_id: DEPT,
  target_date: DATE,
  forecast_id: null,
  model_version: "v-test",
  base,
  options,
  pareto_ids: ["m0.a0.v2", "m0.a1.v2", "m1.a0.v2"],
  minimum_change_id: "m0.a1.v2",
  target: { type: "p50_hours", value: 10 },
  message:
    "Add 1 staff starting at 11:00. Predicted overtime drops from 12 to 9.5 hours (most likely).",
  bounds: {
    morning_staff_present: [3, 4],
    aft_11_staff: [2, 3],
    aft_13_staff: [1, 1],
    outside_support_staff: [1, 1],
    ot_available_staff: [1, 2],
  },
  window_hours: HOURS,
  applied: false,
  applied_option_id: null,
  applied_at: null,
  created_at: "2026-11-02T21:00:00+00:00",
  disclaimer: "Model estimate, not a guarantee.",
};

const plan = {
  department_id: DEPT,
  date: DATE,
  suggested: false,
  status: "final",
  values: {
    regular_patients: 410,
    mf_cases: 20,
    student_clinic_sessions: 4,
    sterilizers_up: 2,
    ...BASE,
  },
  sources: {},
  missing: [],
  updated_at: "2026-11-02T20:00:00+00:00",
};

const problem = (status: number, type: string) =>
  HttpResponse.json(
    { type, title: "x", status },
    { status, headers: { "Content-Type": "application/problem+json" } },
  );

function setup({ latest = scenario as object | null } = {}) {
  const calls = { run: 0, apply: [] as unknown[] };
  server.use(
    http.get(`${API}/v1/plans/:date`, () => HttpResponse.json(plan)),
    http.get(`${API}/v1/scenarios/latest`, () =>
      latest
        ? HttpResponse.json(latest)
        : problem(404, "https://sterileguard.dev/problems/no-scenario"),
    ),
    http.post(`${API}/v1/scenarios`, () => {
      calls.run += 1;
      return HttpResponse.json(scenario, { status: 201 });
    }),
    http.post(`${API}/v1/scenarios/:id/apply`, async ({ request }) => {
      const body = (await request.json()) as { option_id: string };
      calls.apply.push(body);
      return HttpResponse.json({
        scenario: { ...scenario, applied: true, applied_option_id: body.option_id },
        forecast: {
          id: "f-2",
          department_id: DEPT,
          target_date: DATE,
          model_version: "v-test",
          feature_set: "full",
          ot_p10: 7.5,
          ot_p50: 9.5,
          ot_p90: 12.5,
          burden_class: "moderate",
          burden_probs: { low: 0.3, moderate: 0.6, high: 0.1 },
          thresholds: { low_max: 5, moderate_max: 10, source: "simulated_provisional" },
          trigger: "scenario",
          created_at: "2026-11-02T22:00:00+00:00",
          drivers: [],
          disclaimer: "Model estimate, not a guarantee.",
        },
      });
    }),
  );
  return calls;
}

function renderView(roles: string[]) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <Providers>
      <TooltipProvider>{children}</TooltipProvider>
    </Providers>
  );
  return render(<ScenariosView departmentId={DEPT} roles={roles} date={DATE} />, { wrapper });
}

beforeEach(() => {
  server.resetHandlers();
  vi.useRealTimers();
});

describe("ScenariosView", () => {
  it("shows the recommendation with the disclaimer", async () => {
    setup();
    renderView(["supervisor"]);
    const rec = await screen.findByRole("region", { name: /Recommended minimum change/ });
    expect(rec).toHaveTextContent("Add 1 staff starting at 11:00");
    expect(within(rec).getByText("Model estimate, not a guarantee.")).toBeInTheDocument();
    expect(screen.getByText("Target: at most 10.0 overtime hours.")).toBeInTheDocument();
  });

  it("says when no option meets the target", async () => {
    setup({
      latest: {
        ...scenario,
        minimum_change_id: null,
        message: "Even with +2 staff in every window, predicted overtime stays above the target.",
      },
    });
    renderView(["supervisor"]);
    const rec = await screen.findByRole("region", { name: /No option meets the target/ });
    expect(rec).toHaveTextContent("Even with +2 staff");
    expect(within(rec).getByText("Model estimate, not a guarantee.")).toBeInTheDocument();
  });

  it("updates the result 400 ms after a stepper change", async () => {
    setup();
    renderView(["supervisor"]);
    const card = await screen.findByRole("region", { name: "Predicted overtime with these staff" });
    expect(card).toHaveTextContent("Plan as is: 12.0");
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "One more: 11:00 AM start" }));
    expect(card).toHaveTextContent("Most likely 12.0");
    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(card).toHaveTextContent("Most likely 9.5, range 7.5 to 12.5");
    expect(screen.getByRole("button", { name: "One more: 11:00 AM start" })).toBeDisabled();
  });

  it("flags low-confidence options", async () => {
    setup();
    renderView(["supervisor"]);
    await screen.findByRole("region", { name: "Predicted overtime with these staff" });
    fireEvent.click(screen.getByRole("button", { name: "One more: 7:00 AM staff" }));
    fireEvent.click(screen.getByRole("button", { name: "One more: 11:00 AM start" }));
    expect(await screen.findByText(/Low confidence: this staffing is outside/)).toBeInTheDocument();
  });

  it("pins up to three options and compares them", async () => {
    setup();
    renderView(["supervisor"]);
    const card = await screen.findByRole("region", { name: "Predicted overtime with these staff" });
    const shows = (text: string) => waitFor(() => expect(card).toHaveTextContent(text));
    const pin = () => fireEvent.click(screen.getByRole("button", { name: /Pin to compare/ }));
    pin();
    fireEvent.click(screen.getByRole("button", { name: "One more: 11:00 AM start" }));
    await shows("Most likely 9.5");
    pin();
    fireEvent.click(screen.getByRole("button", { name: "One more: 7:00 AM staff" }));
    await shows("Most likely 6.5");
    pin();
    fireEvent.click(screen.getByRole("button", { name: "One fewer: 11:00 AM start" }));
    await shows("Most likely 9.0");
    expect(screen.getByRole("button", { name: "3 pinned" })).toBeDisabled();
    const table = screen.getByRole("table", { name: "Pinned staffing options side by side" });
    expect(within(table).getAllByRole("columnheader")).toHaveLength(4);
    expect(table).toHaveTextContent("+1 at 11:00");
    fireEvent.click(screen.getByRole("button", { name: "Unpin option 1" }));
    expect(screen.getByText("2 of 3 pinned")).toBeInTheDocument();
  });

  it("applies an option after confirming the exact changes", async () => {
    const calls = setup();
    renderView(["supervisor"]);
    const rec = await screen.findByRole("region", { name: /Recommended minimum change/ });
    fireEvent.click(within(rec).getByRole("button", { name: "Show this option" }));
    fireEvent.click(screen.getByRole("button", { name: "Apply to tomorrow's plan" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("11:00 AM start: 2 to 3");
    expect(dialog).toHaveTextContent("Model estimate, not a guarantee.");
    fireEvent.click(within(dialog).getByRole("button", { name: "Apply changes" }));
    await waitFor(() =>
      expect(calls.apply).toEqual([{ department_id: DEPT, option_id: "m0.a1.v2" }]),
    );
    expect(await screen.findByRole("button", { name: "Applied" })).toBeDisabled();
  });

  it("runs scenarios automatically when none exist yet", async () => {
    const calls = setup({ latest: null });
    renderView(["supervisor"]);
    await screen.findByRole("region", { name: /Recommended minimum change/ });
    expect(calls.run).toBe(1);
  });

  it("is read-only for technicians", async () => {
    const calls = setup();
    renderView(["technician"]);
    await screen.findByRole("region", { name: "Predicted overtime with these staff" });
    expect(
      screen.queryByRole("button", { name: "Apply to tomorrow's plan" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Run again/ })).not.toBeInTheDocument();
    expect(calls.run).toBe(0);
  });
});
