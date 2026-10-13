/** Shared CRM vocabulary and display helpers (pipeline stages, phones).
 *
 * Stages mirror ``CRM_STAGES`` in backend/src/nexus/database/models.py — keep
 * both lists in the same funnel order.
 */

export const CRM_STAGES = ["New", "Contacted", "Qualified", "Proposal", "Customer", "Lost"] as const;
export type CrmStage = (typeof CRM_STAGES)[number];

export const STAGE_TONE: Record<string, string> = {
  New: "border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] text-[var(--vbase-slate600)]",
  Contacted: "border-[var(--vbase-indigo)]/30 bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]",
  Qualified: "border-[var(--vbase-amber)]/30 bg-[var(--vbase-amber)]/10 text-[var(--vbase-amber)]",
  Proposal: "border-[var(--vbase-amber)]/30 bg-[var(--vbase-amber)]/10 text-[var(--vbase-amber)]",
  Customer: "border-[var(--vbase-green)]/30 bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]",
  Lost: "border-[var(--vbase-red)]/30 bg-[var(--vbase-red)]/10 text-[var(--vbase-red)]",
};

export function stageTone(stage?: string | null): string {
  return STAGE_TONE[stage || ""] || STAGE_TONE.New;
}

export interface ParsedPhone {
  /** Canonical display form (separators stripped, country code preserved). */
  display: string;
  /** True when the number carries an explicit international prefix. */
  hasCountryCode: boolean;
}

/** Client-side mirror of backend nexus/core/phones.py for display purposes. */
export function parsePhone(raw: string | null | undefined): ParsedPhone | null {
  if (raw == null) return null;
  let text = String(raw).trim();
  if (!text) return null;
  text = text.replace(/\s*(?:ext\.?|x|extension)\s*:?\s*\d+\s*$/i, "").trim();
  if (!text) return null;
  let hasPlus = text.startsWith("+");
  let working = text;
  if (working.startsWith("00")) {
    working = `+${working.slice(2)}`;
    hasPlus = true;
  }
  const digits = working.replace(/\D/g, "");
  if (!digits) return null;
  return { display: hasPlus ? `+${digits}` : digits, hasCountryCode: hasPlus };
}

/** Short country-code hint shown next to a phone number.
 *
 * Only the unambiguous North-American +1 case is extracted (11 digits
 * starting with 1); anything else returns the full international prefix
 * marker "+" so the UI never displays a guessed country code.
 */
export function countryCodeHint(raw: string | null | undefined): string | null {
  const parsed = parsePhone(raw);
  if (!parsed || !parsed.hasCountryCode) return null;
  const digits = parsed.display.slice(1);
  if (digits.length === 11 && digits.startsWith("1")) return "+1";
  return "+";
}
