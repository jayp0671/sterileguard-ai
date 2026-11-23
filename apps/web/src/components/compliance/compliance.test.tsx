import { fireEvent, render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuditDiff } from "@/components/admin/admin-views";
import { diffKeys } from "@/hooks/use-admin";
import { CONSENT_COOKIE, currentConsent, openCookieSettings, parseConsent } from "@/lib/consent";
import { inline, legalIndex, parseFrontmatter, parseMarkdown, readLegal } from "@/lib/legal";
import { API, server } from "@/test/msw";
import { CookieBanner } from "./cookie-banner";
import { PolicyDialog } from "./policy-gate";
import { FOOTER_NOTICE, SiteFooter } from "./site-footer";

function clearCookie() {
  document.cookie = `${CONSENT_COOKIE}=; Max-Age=0; Path=/`;
}

describe("legal content", () => {
  it("every page exists with semver frontmatter and the draft status", () => {
    const pages = legalIndex();
    expect(pages.map((p) => p.slug)).toHaveLength(11);
    for (const p of pages) {
      expect(p.version).toMatch(/^\d+\.\d+\.\d+$/);
      expect(p.effective_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(p.status).toBe("draft, needs human review");
    }
  });

  it("never claims HIPAA compliance", () => {
    const hipaa = JSON.stringify(readLegal("hipaa-notice"));
    expect(hipaa).toContain("not");
    expect(hipaa).toContain("HIPAA compliant");
    for (const p of legalIndex()) {
      const text = JSON.stringify(readLegal(p.slug)).toLowerCase();
      expect(text).not.toMatch(/\bis hipaa[- ]compliant\b|\bhipaa[- ]certified\b(?! or)/);
    }
  });

  it("parses frontmatter, headings, lists and tables", () => {
    const { meta, body } = parseFrontmatter(
      "---\ntitle: T\nversion: 1.2.3\n---\n## A b\n\n- one\n- two\n\n| x | y |\n| --- | --- |\n| 1 | **2** |\n",
    );
    expect(meta).toEqual({ title: "T", version: "1.2.3" });
    const blocks = parseMarkdown(body);
    expect(blocks.map((b) => b.t)).toEqual(["h2", "ul", "table"]);
    expect(blocks[0]).toMatchObject({ id: "a-b" });
  });

  it("drops unsafe links", () => {
    const unsafe = inline("[x](javascript:alert(1))");
    expect(unsafe.some((p) => p.t === "link")).toBe(false);
    expect(unsafe.map((p) => p.v).join("")).toBe("[x](javascript:alert(1))");
    expect(inline("[ok](/trust/terms)")).toEqual([{ t: "link", v: "ok", href: "/trust/terms" }]);
  });
});

describe("footer", () => {
  it("shows the notice and the legal links", () => {
    render(<SiteFooter />);
    expect(screen.getByText(FOOTER_NOTICE)).toBeInTheDocument();
    for (const name of ["Privacy", "Terms", "HIPAA Notice", "Cookies", "Accessibility"]) {
      expect(screen.getByRole("link", { name })).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: "Cookie settings" })).toBeInTheDocument();
  });
});

describe("cookie banner", () => {
  const logged: unknown[] = [];
  beforeEach(() => {
    clearCookie();
    logged.length = 0;
    server.use(
      http.post(`${API}/v1/consents`, async ({ request }) => {
        logged.push(await request.json());
        return HttpResponse.json({ recorded: true, analytics: false }, { status: 201 });
      }),
    );
  });
  afterEach(() => {
    clearCookie();
    vi.unstubAllGlobals();
  });

  it("Essential only stores the choice, logs it, and loads no analytics script", async () => {
    render(<CookieBanner />);
    fireEvent.click(await screen.findByRole("button", { name: "Essential only" }));
    expect(currentConsent()?.analytics).toBe(false);
    expect(document.querySelector('script[src*="posthog"]')).toBeNull();
    await vi.waitFor(() => expect(logged).toHaveLength(1));
    expect(logged[0]).toMatchObject({ version: "1.0.0", analytics: false, gpc: false });
    expect(screen.queryByRole("region", { name: "Cookie choices" })).toBeNull();
  });

  it("treats Global Privacy Control as an opt-out without asking", async () => {
    vi.stubGlobal("navigator", { ...navigator, globalPrivacyControl: true });
    render(<CookieBanner />);
    await vi.waitFor(() => expect(currentConsent()?.analytics).toBe(false));
    expect(screen.queryByRole("button", { name: "Accept analytics" })).toBeNull();
  });

  it("the footer link reopens the preference center", async () => {
    render(<CookieBanner />);
    fireEvent.click(await screen.findByRole("button", { name: "Essential only" }));
    openCookieSettings();
    expect(await screen.findByRole("dialog", { name: "Cookie settings" })).toBeInTheDocument();
  });

  it("parses the cookie", () => {
    const v = encodeURIComponent(JSON.stringify({ version: "1.0.0", analytics: true, ts: "t" }));
    expect(parseConsent(`a=1; ${CONSENT_COOKIE}=${v}`)?.analytics).toBe(true);
    expect(parseConsent(`${CONSENT_COOKIE}=garbage`)).toBeNull();
  });
});

describe("policy acceptance", () => {
  it("cannot be accepted without the checkbox", () => {
    const onAccept = vi.fn();
    const pending = [
      { policy: "terms" as const, version: "1.0.0", accepted: false },
      { policy: "privacy" as const, version: "1.0.0", accepted: false },
    ];
    const { rerender } = render(
      <PolicyDialog
        pending={pending}
        checked={false}
        onCheck={() => {}}
        busy={false}
        onAccept={onAccept}
      />,
    );
    expect(screen.getByRole("link", { name: "Terms of Use" })).toHaveAttribute(
      "href",
      "/trust/terms",
    );
    expect(screen.getByRole("button", { name: "Accept and continue" })).toBeDisabled();
    rerender(
      <PolicyDialog
        pending={pending}
        checked
        onCheck={() => {}}
        busy={false}
        onAccept={onAccept}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Accept and continue" }));
    expect(onAccept).toHaveBeenCalled();
  });
});

describe("audit diff", () => {
  it("shows only changed fields with before and after", () => {
    expect(diffKeys({ a: 1, b: 2 }, { a: 1, b: 3, c: 4 })).toEqual(["b", "c"]);
    render(
      <AuditDiff
        row={{
          id: 1,
          occurred_at: "2026-11-23T10:00:00Z",
          action: "update",
          entity: "memberships",
          before: { role: "technician", user_id: "u" },
          after: { role: "supervisor", user_id: "u" },
        }}
      />,
    );
    expect(screen.getByText("role")).toBeInTheDocument();
    expect(screen.getByText('"technician"')).toBeInTheDocument();
    expect(screen.getByText('"supervisor"')).toBeInTheDocument();
    expect(screen.queryByText("user_id")).toBeNull();
  });
});
