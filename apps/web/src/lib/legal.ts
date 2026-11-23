import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

/**
 * Trust Center content (SG-25): one Markdown file per page in src/content/legal/en, with
 * frontmatter (title, version, effective_date, status). Plain Markdown, not MDX: the pages are
 * text and tables, and a small parser keeps raw HTML out (nothing is rendered unescaped).
 */

export const LEGAL_DIR = path.join(process.cwd(), "src", "content", "legal", "en");

export const LEGAL_ORDER = [
  "privacy",
  "terms",
  "hipaa-notice",
  "cookies",
  "accessibility",
  "ai-transparency",
  "security",
  "data-retention",
  "subprocessors",
  "employee-data-notice",
  "licenses",
] as const;
export type LegalSlug = (typeof LEGAL_ORDER)[number];

export type LegalMeta = {
  slug: string;
  title: string;
  version: string;
  effective_date: string;
  status?: string;
};

export type Inline =
  | { t: "text" | "bold" | "code"; v: string }
  | { t: "link"; v: string; href: string };
export type Block =
  | { t: "h2"; id: string; text: string }
  | { t: "h3"; text: string }
  | { t: "p"; parts: Inline[] }
  | { t: "ul"; items: Inline[][] }
  | { t: "table"; head: Inline[][]; rows: Inline[][][] };

export function parseFrontmatter(raw: string): { meta: Record<string, string>; body: string } {
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(raw);
  if (!m) return { meta: {}, body: raw };
  const meta: Record<string, string> = {};
  for (const line of (m[1] ?? "").split(/\r?\n/)) {
    const i = line.indexOf(":");
    if (i > 0) meta[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  }
  return { meta, body: raw.slice(m[0].length) };
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\))/g;

export function inline(text: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const m of text.matchAll(INLINE)) {
    const tok = m[0];
    if (m.index > last) out.push({ t: "text", v: text.slice(last, m.index) });
    if (tok.startsWith("**")) out.push({ t: "bold", v: tok.slice(2, -2) });
    else if (tok.startsWith("`")) out.push({ t: "code", v: tok.slice(1, -1) });
    else {
      const lm = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(tok);
      const href = lm?.[2] ?? "";
      // Only site paths, https and mailto: never javascript: or data: links.
      if (lm && /^(\/|https:\/\/|mailto:)/.test(href))
        out.push({ t: "link", v: lm[1] ?? "", href });
      else out.push({ t: "text", v: tok });
    }
    last = m.index + tok.length;
  }
  if (last < text.length) out.push({ t: "text", v: text.slice(last) });
  return out;
}

const cells = (row: string) =>
  row
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((c) => inline(c.trim()));

export function parseMarkdown(body: string): Block[] {
  const lines = body.split(/\r?\n/);
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i] ?? "";
    if (!line.trim()) {
      i++;
    } else if (line.startsWith("## ")) {
      const text = line.slice(3).trim();
      blocks.push({ t: "h2", id: slugify(text), text });
      i++;
    } else if (line.startsWith("### ")) {
      blocks.push({ t: "h3", text: line.slice(4).trim() });
      i++;
    } else if (line.trim().startsWith("|")) {
      const rows: string[] = [];
      while (i < lines.length && (lines[i] ?? "").trim().startsWith("|"))
        rows.push(lines[i++] ?? "");
      const [head, , ...rest] = rows;
      blocks.push({ t: "table", head: cells(head ?? ""), rows: rest.map(cells) });
    } else if (/^\s*- /.test(line)) {
      const items: Inline[][] = [];
      while (i < lines.length && /^\s*(- |\s{2,}\S)/.test(lines[i] ?? "")) {
        const l = lines[i++] ?? "";
        if (/^\s*- /.test(l)) items.push(inline(l.replace(/^\s*- /, "")));
        else {
          const lastItem = items[items.length - 1];
          if (lastItem) lastItem.push({ t: "text", v: ` ${l.trim()}` }, ...[]);
        }
      }
      blocks.push({ t: "ul", items });
    } else {
      const para: string[] = [];
      while (
        i < lines.length &&
        (lines[i] ?? "").trim() &&
        !/^(## |### |\||\s*- )/.test(lines[i] ?? "")
      )
        para.push((lines[i++] ?? "").trim());
      blocks.push({ t: "p", parts: inline(para.join(" ")) });
    }
  }
  return blocks;
}

export function readLegal(slug: string): { meta: LegalMeta; blocks: Block[] } | null {
  if (!(LEGAL_ORDER as readonly string[]).includes(slug)) return null;
  const raw = readFileSync(path.join(LEGAL_DIR, `${slug}.md`), "utf8");
  const { meta, body } = parseFrontmatter(raw);
  return {
    meta: {
      slug,
      title: meta.title ?? slug,
      version: meta.version ?? "0.0.0",
      effective_date: meta.effective_date ?? "",
      status: meta.status,
    },
    blocks: parseMarkdown(body),
  };
}

export function legalIndex(): LegalMeta[] {
  const present = new Set(readdirSync(LEGAL_DIR).map((f) => f.replace(/\.md$/, "")));
  return LEGAL_ORDER.filter((s) => present.has(s)).flatMap((s) => {
    const page = readLegal(s);
    return page ? [page.meta] : [];
  });
}
