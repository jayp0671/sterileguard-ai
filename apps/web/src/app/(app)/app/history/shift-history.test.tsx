import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { API, server } from "@/test/msw";
import { Providers } from "@/test/render";
import { ShiftHistory } from "./shift-history";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const DEPT = "00000000-0000-4000-8000-000000000003";
const row = (id: string, date: string, status: string, extra: object = {}) => ({
  id,
  department_id: DEPT,
  shift_date: date,
  ot_labor_hours: 9,
  status,
  source: "real",
  author_role: "technician",
  mine: false,
  created_at: "2026-11-02T20:00:00Z",
  updated_at: "2026-11-02T20:00:00Z",
  forecast: null,
  error: null,
  inside_range: null,
  ...extra,
});

function setup() {
  const approved: string[] = [];
  server.use(
    http.get(`${API}/v1/shifts`, () =>
      HttpResponse.json({
        items: [
          row("a", "2026-10-30", "submitted", {
            forecast: { ot_p10: 6, ot_p50: 7.5, ot_p90: 10, model_version: "v" },
            error: 1.5,
            inside_range: true,
          }),
          row("b", "2026-10-29", "approved", {
            forecast: { ot_p10: 2, ot_p50: 3, ot_p90: 5, model_version: "v" },
            error: 6,
            inside_range: false,
          }),
        ],
        has_more: false,
        next_offset: null,
      }),
    ),
    http.post(`${API}/v1/shifts/:id/approve`, ({ params }) => {
      approved.push(String(params.id));
      return HttpResponse.json(row(String(params.id), "2026-10-30", "approved"));
    }),
  );
  return approved;
}

function renderHistory(roles: string[]) {
  const wrapper = ({ children }: { children: ReactNode }) => <Providers>{children}</Providers>;
  return render(<ShiftHistory departmentId={DEPT} roles={roles} />, { wrapper });
}

beforeEach(() => server.resetHandlers());

describe("ShiftHistory", () => {
  it("shows predicted vs actual error and range hits", async () => {
    setup();
    renderHistory(["technician"]);
    const table = await screen.findByRole("table", { name: "Shift history" });
    const first = within(table).getAllByRole("row")[1] as HTMLElement;
    expect(first).toHaveTextContent("2026-10-30");
    expect(first).toHaveTextContent("+1.5");
    expect(first).toHaveTextContent("Yes");
    expect(within(table).getAllByRole("row")[2]).toHaveTextContent("No");
    expect(screen.queryByRole("button", { name: /Approve selected/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Export CSV/ })).not.toBeInTheDocument();
  });

  it("lets supervisors bulk-approve submitted rows after confirming", async () => {
    const approved = setup();
    renderHistory(["supervisor"]);
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select 2026-10-30" }));
    expect(screen.queryByRole("checkbox", { name: "Select 2026-10-29" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Approve selected (1)" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Approved rows are locked");
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(approved).toEqual(["a"]));
  });
});
