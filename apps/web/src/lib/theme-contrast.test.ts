/**
 * Contrast regression guard.
 *
 * Dark mode shipped with native controls that stayed light-themed and text that
 * resolved to white-on-white, because a single CSS selector was wrong. Nothing
 * caught it, so this test locks the contract down: it parses the *actual* colour
 * tokens out of ``index.css`` and asserts WCAG contrast for the pairs the design
 * system promises, in both themes.
 *
 * It deliberately works on the stylesheet rather than a rendered DOM: no browser
 * is needed in CI, and a token edit that breaks a pair fails here immediately.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const CSS_PATH = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../index.css");
const css = readFileSync(CSS_PATH, "utf-8");

type Rgb = { r: number; g: number; b: number };

function hexToRgb(value: string): Rgb {
  const hex = value.trim().replace(/^#/, "");
  const full = hex.length === 3 ? hex.split("").map((c) => c + c).join("") : hex;
  if (!/^[0-9a-fA-F]{6}$/.test(full)) throw new Error(`not a hex colour: ${value}`);
  return {
    r: parseInt(full.slice(0, 2), 16),
    g: parseInt(full.slice(2, 4), 16),
    b: parseInt(full.slice(4, 6), 16),
  };
}

function luminance({ r, g, b }: Rgb): number {
  const channel = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(a: string, b: string): number {
  const la = luminance(hexToRgb(a));
  const lb = luminance(hexToRgb(b));
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** Declarations from the first rule whose selector matches exactly. */
function declarations(selector: string): Record<string, string> {
  const index = css.indexOf(`${selector} {`);
  if (index === -1) throw new Error(`rule not found in index.css: ${selector}`);
  const body = css.slice(css.indexOf("{", index) + 1, css.indexOf("}", index));
  const out: Record<string, string> = {};
  for (const line of body.split("\n")) {
    const match = line.match(/^\s*(--[\w-]+)\s*:\s*([^;]+);/);
    if (match) out[match[1]] = match[2].trim();
  }
  return out;
}

const LIGHT = declarations(":root");
const DARK = declarations(".dark");

/**
 * Resolve a token the way the cascade does: a theme value wins, otherwise the
 * `:root` value applies (that is why shared tokens such as the terminal pair
 * only need declaring once).
 */
function token(theme: Record<string, string>, name: string): string {
  const raw = theme[name] ?? LIGHT[name];
  if (!raw) throw new Error(`token ${name} is not defined in any theme`);
  const indirect = raw.match(/^var\((--[\w-]+)/);
  return indirect ? token(theme, indirect[1]) : raw;
}

/**
 * The contract, as (foreground token, surface token, minimum ratio) triples.
 *
 * Body copy and UI labels must clear AA (4.5:1). Heading tokens are held to
 * 7:1 because they are large and the theme owes them more headroom than the
 * minimum. Accent chips (a light accent on its own 10% tint) are intentionally
 * not listed here — they are a deliberate, separate part of the visual language.
 */
const TEXT_PAIRS: Array<[string, string, number]> = [
  ["--vbase-slate900", "--vbase-bg", 7],
  ["--vbase-slate800", "--vbase-bg", 7],
  ["--vbase-slate700", "--vbase-bg", 4.5],
  ["--vbase-slate600", "--vbase-bg", 4.5],
  ["--vbase-slate500", "--vbase-bg", 4.5],
  ["--vbase-slate700", "--vbase-bg-alt", 4.5],
  ["--vbase-slate500", "--vbase-bg-alt", 4.5],
  ["--vbase-slate600", "--vbase-muted-bg", 4.5],
  ["--vbase-indigo", "--vbase-bg", 4.5],
];

const themes: Array<[string, Record<string, string>]> = [
  ["light", LIGHT],
  ["dark", DARK],
];

describe("theme contrast", () => {
  for (const [name, theme] of themes) {
    it(`${name}: text clears the documented ratio on every surface`, () => {
      const failures: string[] = [];
      for (const [fg, bg, minimum] of TEXT_PAIRS) {
        const ratio = contrast(token(theme, fg), token(theme, bg));
        if (ratio < minimum) {
          failures.push(`${fg} on ${bg}: ${ratio.toFixed(2)} < ${minimum}`);
        }
      }
      expect(failures).toEqual([]);
    });

    it(`${name}: the terminal block stays dark with legible text`, () => {
      const ratio = contrast(token(theme, "--vbase-terminal-fg"), token(theme, "--vbase-terminal-bg"));
      expect(ratio).toBeGreaterThanOrEqual(7);
    });
  }

  it("both themes flip every surface and text token", () => {
    // A token defined only in :root silently keeps its light value in dark mode,
    // which is exactly how the original white-on-white select happened.
    const missing = Object.keys(LIGHT).filter((key) => !(key in DARK));
    // Terminal tokens are intentionally identical in both themes.
    const intentionallyShared = new Set(["--vbase-terminal-bg", "--vbase-terminal-fg"]);
    expect(missing.filter((key) => !intentionallyShared.has(key))).toEqual([]);
  });

  it("filled buttons carry white text above AA", () => {
    for (const selector of [".vbase-btn-primary", ".vbase-btn-danger"]) {
      const index = css.indexOf(`${selector} {`);
      const body = css.slice(css.indexOf("{", index) + 1, css.indexOf("}", index));
      const background = body.match(/background-color:\s*(#[0-9a-fA-F]{6})/)?.[1];
      expect(background, `${selector} must declare a literal background`).toBeTruthy();
      expect(contrast("#ffffff", background!)).toBeGreaterThanOrEqual(4.5);
    }
  });
});
