/**
 * WCAG contrast check for every text/background and UI-border pair in tokens.css (SG-10).
 * Run by `sg test a11y --tokens` and the normal Vitest suite.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { contrastRatio, parseThemes } from "./contrast";

const css = readFileSync(join(__dirname, "tokens.css"), "utf8");
const themes = parseThemes(css);

const TEXT_PAIRS: [string, string][] = [
  ["foreground", "background"],
  ["foreground", "card"],
  ["card-foreground", "card"],
  ["popover-foreground", "popover"],
  ["muted-foreground", "background"],
  ["muted-foreground", "card"],
  ["muted-foreground", "muted"],
  ["primary-foreground", "primary"],
  ["primary", "background"],
  ["primary", "card"],
  ["secondary-foreground", "secondary"],
  ["accent-foreground", "accent"],
  ["destructive-foreground", "destructive"],
  ["destructive", "card"],
  ["sidebar-foreground", "sidebar"],
  ["sidebar-accent-foreground", "sidebar-accent"],
  ["sidebar-primary-foreground", "sidebar-primary"],
  ...(["good", "warning", "critical", "info"] as const).map(
    (s) => [`status-${s}-fg`, `status-${s}-bg`] as [string, string],
  ),
];
// Non-text UI: form control borders and the focus ring need 3:1 against the surface.
const UI_PAIRS: [string, string][] = [
  ["input", "background"],
  ["input", "card"],
  ["ring", "background"],
  ["ring", "card"],
];

describe.each(["light", "dark"] as const)("%s theme contrast", (theme) => {
  const t = themes[theme];

  it.each(TEXT_PAIRS)("%s on %s >= 4.5:1", (fg, bg) => {
    expect(contrastRatio(t[fg], t[bg])).toBeGreaterThanOrEqual(4.5);
  });

  it.each(UI_PAIRS)("%s on %s >= 3:1", (fg, bg) => {
    expect(contrastRatio(t[fg], t[bg])).toBeGreaterThanOrEqual(3);
  });
});

describe("contrast math", () => {
  it("matches the WCAG reference values", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrastRatio("#777777", "#ffffff")).toBeCloseTo(4.48, 2);
  });
});
