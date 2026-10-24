/** WCAG 2.x relative luminance and contrast ratio (https://www.w3.org/TR/WCAG21/#dfn-contrast-ratio). */

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

export function luminance(hex: string): number {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? [...h].map((x) => x + x).join("") : h;
  const [r = 0, g = 0, b = 0] = [0, 2, 4].map((i) => Number.parseInt(full.slice(i, i + 2), 16));
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrastRatio(a: string | undefined, b: string | undefined): number {
  if (!a || !b) throw new Error(`missing color: ${a} / ${b}`);
  const [hi = 0, lo = 0] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** Hex custom properties per theme: `:root` is light, `.dark` overrides it. */
export function parseThemes(css: string): Record<"light" | "dark", Record<string, string>> {
  const block = (selector: string) => {
    const start = css.indexOf(`${selector} {`);
    const body = css.slice(start, css.indexOf("}", start));
    const vars: Record<string, string> = {};
    for (const [, name, hex] of body.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{3,6})\s*;/g)) {
      if (name && hex) vars[name] = hex;
    }
    return vars;
  };
  const light = block(":root");
  return { light, dark: { ...light, ...block(".dark") } };
}
