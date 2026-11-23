import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { checkUpload, type ImportJob, phiBannerText } from "@/hooks/use-imports";
import { API, server } from "@/test/msw";
import { Providers } from "@/test/render";
import { ReviewScreen } from "./imports-view";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// cmdk (the searchable field select) measures its list; jsdom has neither API.
beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  Element.prototype.scrollIntoView ??= () => {};
});

const DEPT = "00000000-0000-4000-8000-000000000003";
const JOB = "00000000-0000-4000-8000-0000000000aa";
const fields = [
  { name: "date", label: "Date", description: "Shift date", unit: "", tier: 1, required: true },
  {
    name: "regular_patients",
    label: "Regular patients",
    description: "Patients",
    unit: "patients",
    tier: 1,
    required: true,
  },
  {
    name: "student_clinic_sessions",
    label: "Student clinic sessions",
    description: "Sessions",
    unit: "sessions",
    tier: 2,
    required: false,
  },
  { name: "notes", label: "Notes", description: "Free text", unit: "", tier: 3, required: false },
];

const job: ImportJob = {
  id: JOB,
  department_id: DEPT,
  original_filename: "week-1.csv",
  status: "validated",
  rows_committed: null,
  created_by_me: true,
  created_at: "2026-11-23T12:00:00Z",
  updated_at: "2026-11-23T12:00:00Z",
  file_available: true,
  parse: {
    file_type: "csv",
    sheet: null,
    sheets: [],
    header_rows: [0],
    rows: 5,
    columns: 6,
    wide: false,
    transform_notes: [],
    error: null,
  },
  phi: { columns_removed: 1, cells_blocked: 2, rows_flagged: 2 },
  columns: [
    {
      column: "Date",
      field: "date",
      method: "exact",
      confidence: 1,
      uncertain: false,
      dtype: "date",
      samples: ["2026-10-12"],
      phi_flagged: false,
    },
    {
      column: "Clinic blocks",
      field: null,
      suggested_field: "student_clinic_sessions",
      method: "ai",
      confidence: 0.45,
      uncertain: true,
      dtype: "number",
      samples: ["4", "3"],
      phi_flagged: false,
    },
    {
      column: "Notes",
      field: "notes",
      method: "exact",
      confidence: 1,
      uncertain: false,
      dtype: "text",
      samples: [],
      phi_flagged: true,
    },
  ],
  validation: {
    valid_rows: 4,
    invalid_rows: 1,
    errors: [
      {
        row: 3,
        column: "regular_patients",
        value: "9999",
        message: "above the maximum 800",
        kind: "invalid",
      },
      { row: 0, column: null, value: null, message: "blocked", kind: "blocked" },
    ],
    preview: [
      {
        row: 0,
        cells: {
          date: { value: "2026-10-12", original: "10/12/2026", changed: true, hidden: false },
          regular_patients: { value: 332, original: "332", changed: false, hidden: false },
          notes: { value: null, original: null, changed: false, hidden: true },
        },
      },
    ],
  },
};

function renderReview(over: Partial<ImportJob> = {}) {
  return render(
    <Providers>
      <ReviewScreen departmentId={DEPT} job={{ ...job, ...over }} fields={fields} isAdmin={false} />
    </Providers>,
  );
}

describe("ReviewScreen", () => {
  it("shows the PHI banner as counts only and hides flagged samples", () => {
    renderReview();
    expect(
      screen.getByText(
        /1 column was removed because it looked like names or IDs\. 2 cells were blocked\./,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Hidden (possible identifiers)")).toBeInTheDocument();
    expect(screen.getByText("text (hidden)")).toBeInTheDocument();
  });

  it("marks low-confidence AI suggestions as uncertain without applying them", () => {
    renderReview();
    expect(screen.getByText("Uncertain 45%")).toBeInTheDocument();
    expect(
      screen.getByRole("combobox", { name: "Field for column Clinic blocks" }),
    ).toHaveTextContent("Suggested: Student clinic sessions");
    expect(screen.getByText(/AI suggestions are shown but never applied/)).toBeInTheDocument();
  });

  it("lists validation errors and the commit count", () => {
    renderReview();
    expect(screen.getByText("above the maximum 800")).toBeInTheDocument();
    expect(screen.getByText("Cell blocked; row still imports")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Commit 4 valid rows" })).toBeEnabled();
  });

  it("remaps a column through the API", async () => {
    let body: unknown;
    server.use(
      http.patch(`${API}/v1/imports/${JOB}/mapping`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(job);
      }),
    );
    renderReview();
    fireEvent.click(screen.getByRole("combobox", { name: "Field for column Clinic blocks" }));
    fireEvent.click(await screen.findByText("Student clinic sessions (suggested)"));
    await waitFor(() =>
      expect(body).toEqual({
        department_id: DEPT,
        mapping: { "Clinic blocks": "student_clinic_sessions" },
      }),
    );
  });

  it("disables actions once committed", () => {
    renderReview({ status: "committed" });
    expect(screen.getByRole("button", { name: "Commit 4 valid rows" })).toBeDisabled();
  });
});

describe("upload helpers", () => {
  it("checks type and size before uploading", () => {
    expect(checkUpload(new File(["x"], "a.pdf"))).toMatch(/csv/);
    expect(checkUpload(new File([], "a.csv"))).toMatch(/empty/);
    expect(checkUpload(new File(["a,b"], "a.csv"))).toBeNull();
  });

  it("writes the banner sentence", () => {
    expect(phiBannerText({ columns_removed: 2, cells_blocked: 3, rows_flagged: 3 })).toBe(
      "2 columns were removed because they looked like names or IDs. 3 cells were blocked.",
    );
    expect(phiBannerText({ columns_removed: 0, cells_blocked: 0, rows_flagged: 0 })).toBeNull();
  });
});
