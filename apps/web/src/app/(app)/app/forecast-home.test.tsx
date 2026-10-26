import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import messages from "@/messages/en.json";
import { API, server } from "@/test/msw";
import { Providers } from "@/test/render";
import { ForecastHome } from "./forecast-home";

const DEPT = "00000000-0000-4000-8000-000000000003";
const DATE = "2026-10-27";

const plan = (suggested: boolean) => ({
  department_id: DEPT,
  date: DATE,
  suggested,
  status: suggested ? null : "final",
  values: {
    regular_patients: 420,
    morning_staff_present: 3,
    mf_cases: 22,
    student_clinic_sessions: 4,
    aft_11_staff: 2,
    aft_13_staff: 1,
    aft_15_staff: 2,
    outside_support_staff: 1,
    ot_available_staff: 2,
    washers_up: 2,
    sterilizers_up: 1,
    carryover_backlog_estimate: 2,
    is_holiday: false,
    academic_event: "none",
  },
  sources: {},
  missing: [],
  updated_at: suggested ? null : "2026-10-26T20:00:00+00:00",
});

const forecast = {
  id: "f-1",
  department_id: DEPT,
  target_date: DATE,
  plan_id: "p-1",
  model_version: "20261026-0036-abc1234",
  feature_set: "full",
  ot_p10: 6.2,
  ot_p50: 8.4,
  ot_p90: 11.1,
  burden_class: "moderate",
  burden_probs: { low: 0.1, moderate: 0.62, high: 0.28 },
  thresholds: { low_max: 5.7, moderate_max: 12.1, source: "simulated_provisional" },
  trigger: "manual",
  created_at: "2026-10-26T21:00:00+00:00",
  disclaimer: "Model estimate, not a guarantee.",
  drivers: [
    {
      rank: 1,
      feature: "ot_available_staff",
      value: "2",
      contribution_hours: 3.1,
      text_key: "drivers.ot_available_staff.pos",
      text_params: { value: 2, hours: 3.1 },
      default_text: "x",
    },
    {
      rank: 2,
      feature: "sterilizers_up",
      value: "1",
      contribution_hours: 1.2,
      text_key: "drivers.sterilizers_up.pos",
      text_params: { value: 1, hours: 1.2 },
      default_text: "x",
    },
    {
      rank: 3,
      feature: "aft_11_staff",
      value: "2",
      contribution_hours: -0.6,
      text_key: "drivers.aft_11_staff.neg",
      text_params: { value: 2, hours: 0.6 },
      default_text: "x",
    },
    {
      rank: 4,
      feature: "other",
      value: null,
      contribution_hours: 0.2,
      text_key: "drivers.other.pos",
      text_params: { hours: 0.2 },
      default_text: "x",
    },
  ],
};

function setup({
  saved = true,
  next = forecast as object | null,
  post = { status: 201, body: forecast as object },
}: {
  saved?: boolean;
  next?: object | null;
  post?: { status: number; body: object };
} = {}) {
  let posted = 0;
  server.use(
    http.get(`${API}/v1/plans/:date`, () => HttpResponse.json(plan(!saved))),
    http.get(`${API}/v1/forecasts/next-day`, () =>
      next
        ? HttpResponse.json(next)
        : HttpResponse.json(
            {
              type: "https://sterileguard.dev/problems/no-forecast",
              title: "Not Found",
              status: 404,
            },
            { status: 404, headers: { "Content-Type": "application/problem+json" } },
          ),
    ),
    http.get(`${API}/v1/forecasts/history`, () =>
      HttpResponse.json([
        { date: "2026-10-22", ot_p10: 4, ot_p50: 6, ot_p90: 8, actual: 7, model_version: "v" },
      ]),
    ),
    http.post(`${API}/v1/forecasts`, () => {
      posted += 1;
      return HttpResponse.json(post.body, {
        status: post.status,
        headers: post.status >= 400 ? { "Content-Type": "application/problem+json" } : undefined,
      });
    }),
  );
  return { posted: () => posted };
}

function renderHome(roles: string[]) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <Providers>
      <NextIntlClientProvider locale="en" messages={messages}>
        <TooltipProvider>{children}</TooltipProvider>
      </NextIntlClientProvider>
    </Providers>
  );
  return render(<ForecastHome departmentId={DEPT} roles={roles} date={DATE} />, { wrapper });
}

beforeEach(() => {
  server.resetHandlers();
});

describe("ForecastHome", () => {
  it("shows skeletons while loading", () => {
    setup();
    renderHome(["supervisor"]);
    expect(screen.getByText("Loading the forecast")).toBeInTheDocument();
  });

  it("shows the estimate, range, burden, drivers and chart", async () => {
    setup();
    renderHome(["supervisor"]);
    expect((await screen.findAllByText("8.4"))[0]).toHaveClass("font-mono");
    expect(
      screen.getByRole("heading", { name: "Tomorrow, Tuesday, October 27" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Most likely/)).toHaveTextContent(
      "Most likely 8.4, range 6.2 to 11.1 (80%)",
    );
    expect(screen.getByText("Moderate burden")).toBeInTheDocument();
    expect(screen.getByText("62%")).toBeInTheDocument();
    expect(screen.getByText(/Categories are provisional/)).toBeInTheDocument();
    expect(screen.getByText("Model estimate, not a guarantee.")).toBeInTheDocument();
    expect(
      screen.getByText("2 staff willing to stay is adding about 3.1 hours"),
    ).toBeInTheDocument();
    expect(screen.getByText("20261026-0036-abc1234")).toBeInTheDocument();
    expect(await screen.findByText(/fell inside the range on 1 of 1 day/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Recompute/ })).toBeInTheDocument();
  });

  it("hides Recompute from technicians", async () => {
    setup();
    renderHome(["technician"]);
    expect((await screen.findAllByText("8.4"))[0]).toHaveClass("font-mono");
    expect(screen.queryByRole("button", { name: /Recompute/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View plan/ })).toHaveAttribute("href", "/app/plan");
  });

  it("asks to plan tomorrow when no plan is saved", async () => {
    setup({ saved: false, next: null });
    renderHome(["supervisor"]);
    expect(await screen.findByText("No plan for tomorrow yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Plan tomorrow" })).toHaveAttribute(
      "href",
      "/app/plan",
    );
  });

  it("computes a forecast from a saved plan", async () => {
    const api = setup({ next: null });
    renderHome(["supervisor"]);
    fireEvent.click(await screen.findByRole("button", { name: "Compute forecast" }));
    expect((await screen.findAllByText("8.4"))[0]).toHaveClass("font-mono");
    expect(api.posted()).toBe(1);
  });

  it("tells technicians the forecast is not computed yet", async () => {
    setup({ next: null });
    renderHome(["technician"]);
    expect(await screen.findByText(/has not computed the forecast/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Compute forecast" })).not.toBeInTheDocument();
  });

  it("shows the request id when the model is not loaded", async () => {
    setup({
      next: null,
      post: {
        status: 503,
        body: {
          type: "https://sterileguard.dev/problems/model-not-loaded",
          title: "Service Unavailable",
          status: 503,
          detail: "no active model is loaded; try again shortly",
          request_id: "req-123",
        },
      },
    });
    renderHome(["supervisor"]);
    fireEvent.click(await screen.findByRole("button", { name: "Compute forecast" }));
    expect(await screen.findByText("The forecast model is not loaded")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("req-123")).toBeInTheDocument());
  });
});
