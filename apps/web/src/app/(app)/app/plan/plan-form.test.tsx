import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { API, server } from "@/test/msw";
import { renderWithProviders } from "@/test/render";
import { AUTOSAVE_MS, describeSource, PlanForm } from "./plan-form";

const DEPT = "00000000-0000-4000-8000-000000000003";
const DATE = "2026-10-27";

const suggested = {
  department_id: DEPT,
  date: DATE,
  suggested: true,
  status: null,
  values: {
    regular_patients: 350,
    morning_staff_present: 3,
    mf_cases: 20,
    student_clinic_sessions: 4,
    aft_11_staff: 3,
    aft_13_staff: 1,
    aft_15_staff: 2,
    outside_support_staff: 2,
    ot_available_staff: 2,
    washers_up: 2,
    sterilizers_up: 2,
    carryover_backlog_estimate: 1,
    is_holiday: false,
    academic_event: "none",
  },
  sources: {
    regular_patients: "history:average of the last 4 Tuesdays",
    mf_cases: "settings:mf_cases_default",
  },
  missing: [],
  updated_at: null,
};

let puts: { body: Record<string, unknown>; key: string | null }[] = [];

beforeEach(() => {
  puts = [];
  server.use(
    http.get(`${API}/v1/plans/:date`, () => HttpResponse.json(suggested)),
    http.put(`${API}/v1/plans/:date`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      puts.push({ body, key: request.headers.get("Idempotency-Key") });
      return HttpResponse.json({
        ...suggested,
        suggested: false,
        status: body.status,
        values: body,
      });
    }),
  );
});

afterEach(() => {
  vi.useRealTimers();
});

function renderForm(canEdit = true) {
  return renderWithProviders(
    <TooltipProvider>
      <PlanForm departmentId={DEPT} canEdit={canEdit} initialDate={DATE} />
    </TooltipProvider>,
  );
}

describe("PlanForm", () => {
  it("shows suggestions with their source", async () => {
    renderForm();
    expect(await screen.findByLabelText("Regular patients")).toHaveValue("350");
    expect(screen.getAllByRole("button", { name: "Suggested" }).length).toBeGreaterThan(0);
    expect(describeSource("settings:mf_cases_default")).toBe(
      "Department setting (mf_cases_default)",
    );
    expect(describeSource("history:average of the last 4 Tuesdays")).toBe(
      "Average of the last 4 Tuesdays",
    );
    expect(describeSource("saved")).toBeNull();
  });

  it("shows field-level errors from the OpenAPI ranges and does not save invalid data", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderForm();
    const input = await screen.findByLabelText("Regular patients");
    fireEvent.change(input, { target: { value: "900" } });
    expect(await screen.findByText(/Regular patients must be at most 800/)).toBeInTheDocument();
    await act(async () => {
      vi.advanceTimersByTime(AUTOSAVE_MS + 100);
    });
    expect(puts).toHaveLength(0);
  });

  it("autosaves one draft 10 seconds after the last change, with an Idempotency-Key", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderForm();
    await screen.findByLabelText("Regular patients");
    fireEvent.click(screen.getByRole("button", { name: "Increase Regular patients" }));
    await act(async () => {
      vi.advanceTimersByTime(5_000);
    });
    fireEvent.click(screen.getByRole("button", { name: "Increase Regular patients" }));
    await act(async () => {
      vi.advanceTimersByTime(AUTOSAVE_MS - 1_000);
    });
    expect(puts).toHaveLength(0); // the second change restarted the 10 s timer
    await act(async () => {
      vi.advanceTimersByTime(1_100);
    });
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]?.body.regular_patients).toBe(352);
    expect(puts[0]?.body.status).toBe("draft");
    expect(puts[0]?.key).toMatch(/[0-9a-f-]{36}/);
  });

  it("finalizes immediately", async () => {
    renderForm();
    await screen.findByLabelText("Regular patients");
    fireEvent.click(screen.getByRole("button", { name: "Finalize plan" }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]?.body.status).toBe("final");
  });

  it("shows a conflict message with a reload option on 409", async () => {
    server.use(
      http.put(`${API}/v1/plans/:date`, () =>
        HttpResponse.json(
          { type: "about:blank", title: "Conflict", status: 409, request_id: "r9" },
          { status: 409, headers: { "content-type": "application/problem+json" } },
        ),
      ),
    );
    renderForm();
    await screen.findByLabelText("Regular patients");
    fireEvent.click(screen.getByRole("button", { name: "Finalize plan" }));
    expect(
      await screen.findByRole("button", { name: /reload the latest plan/i }),
    ).toBeInTheDocument();
  });

  it("is read only for technicians", async () => {
    renderForm(false);
    const input = await screen.findByLabelText("Regular patients");
    expect(input).toHaveAttribute("readonly");
    expect(screen.queryByRole("button", { name: "Finalize plan" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Increase/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Read only/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tomorrow's plan" })).toBeInTheDocument();
  });

  it("shows the request id when loading fails", async () => {
    server.use(
      http.get(`${API}/v1/plans/:date`, () =>
        HttpResponse.json(
          {
            type: "about:blank",
            title: "Not Found",
            status: 404,
            detail: "department not found",
            request_id: "r404",
          },
          { status: 404, headers: { "content-type": "application/problem+json" } },
        ),
      ),
    );
    renderForm();
    expect(await screen.findByText("r404")).toBeInTheDocument();
  });
});
