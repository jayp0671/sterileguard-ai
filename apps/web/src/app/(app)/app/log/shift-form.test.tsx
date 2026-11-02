import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { emptyDraft, saveDraft } from "@/lib/shift-log";
import { API, server } from "@/test/msw";
import { Providers } from "@/test/render";
import { ShiftForm } from "./shift-form";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: vi.fn() }) }));

const DEPT = "00000000-0000-4000-8000-000000000003";

function setup() {
  const calls = { posts: [] as Record<string, unknown>[], submits: 0 };
  server.use(
    http.post(`${API}/v1/shifts`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      calls.posts.push(body);
      return HttpResponse.json(
        {
          id: "s-1",
          department_id: DEPT,
          shift_date: body.shift_date,
          ot_labor_hours: body.ot_labor_hours,
          status: "draft",
          source: "real",
          mine: true,
          created_at: "2026-11-02T20:00:00Z",
          updated_at: "2026-11-02T20:00:00Z",
        },
        { status: 201 },
      );
    }),
    http.patch(`${API}/v1/shifts/:id`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      calls.posts.push(body);
      return HttpResponse.json({ id: "s-1", status: "draft" });
    }),
    http.post(`${API}/v1/shifts/:id/submit`, () => {
      calls.submits += 1;
      return HttpResponse.json({ id: "s-1", status: "submitted" });
    }),
  );
  return calls;
}

function renderForm(roles = ["technician"]) {
  const wrapper = ({ children }: { children: ReactNode }) => <Providers>{children}</Providers>;
  return render(<ShiftForm departmentId={DEPT} roles={roles} />, { wrapper });
}

beforeEach(() => {
  server.resetHandlers();
  window.localStorage.clear();
  push.mockReset();
});

describe("ShiftForm", () => {
  it("adds up end times past 3 PM and submits only the total", async () => {
    const calls = setup();
    renderForm();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("radio", { name: "Who stayed past 3 PM?" }));
    fireEvent.change(screen.getByLabelText("Left at"), { target: { value: "20:00" } });
    fireEvent.click(screen.getByRole("button", { name: /Add a person/ }));
    fireEvent.change(screen.getAllByLabelText("Left at")[1] as HTMLElement, {
      target: { value: "19:30" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Add a person/ }));
    fireEvent.change(screen.getAllByLabelText("Left at")[2] as HTMLElement, {
      target: { value: "18:00" },
    });
    expect(screen.getByText("12.5 h")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Do not enter patient or employee names.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    await waitFor(() => expect(calls.submits).toBe(1));
    const last = calls.posts.at(-1) ?? {};
    expect(last.ot_labor_hours).toBe(12.5);
    expect(JSON.stringify(calls.posts)).not.toContain("19:30");
    expect(push).toHaveBeenCalledWith("/app/history?shift=s-1");
    expect(window.localStorage.getItem(`sg.shift-draft.${DEPT}`)).toBeNull();
  });

  it("recovers an unsent draft from this device", () => {
    setup();
    saveDraft(DEPT, {
      ...emptyDraft("2026-11-02"),
      otTotal: "6.5",
      notes: "washer 2 down",
      step: 0,
      savedAt: "2026-11-02T19:00:00Z",
    });
    renderForm();
    expect(screen.getByText(/restored your unsent draft/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByLabelText("Overtime labor-hours past 3:00 PM")).toHaveValue(6.5);
  });

  it("keeps the draft on the server too", async () => {
    const calls = setup();
    renderForm();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.change(screen.getByLabelText("Overtime labor-hours past 3:00 PM"), {
      target: { value: "4" },
    });
    await waitFor(() => expect(calls.posts).toHaveLength(1), { timeout: 3000 });
    expect(await screen.findByText("Draft saved")).toBeInTheDocument();
  });

  it("offers backfill only to supervisors", () => {
    setup();
    const { unmount } = renderForm(["technician"]);
    expect(screen.queryByText("Log a past day")).not.toBeInTheDocument();
    unmount();
    renderForm(["supervisor"]);
    expect(screen.getByText("Log a past day")).toBeInTheDocument();
  });

  it("shows the server's guard message without the notes", async () => {
    setup();
    server.use(
      http.post(`${API}/v1/shifts`, () =>
        HttpResponse.json(
          {
            type: "https://sterileguard.dev/problems/phi-detected",
            title: "Unprocessable Content",
            status: 422,
            detail: "notes looks like it contains identifiers (EMAIL_ADDRESS).",
          },
          { status: 422, headers: { "Content-Type": "application/problem+json" } },
        ),
      ),
    );
    saveDraft(DEPT, { ...emptyDraft("2026-11-02"), otTotal: "3", step: 3, savedAt: "" });
    renderForm();
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("EMAIL_ADDRESS");
  });
});
