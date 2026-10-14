import { IconPhone } from "@/lib/icons";
import { parsePhone } from "@/lib/crm";

/** Text that never overlaps its neighbours: constrained width, ellipsis,
 *  full value on hover. `title` defaults to the text itself. */
export function ClippedText({
  children,
  title,
  maxWidth = "max-w-[200px]",
  className = "",
}: {
  children: React.ReactNode;
  title?: string;
  maxWidth?: string;
  className?: string;
}) {
  const text = title ?? (typeof children === "string" ? children : undefined);
  return (
    <span className={`block truncate ${maxWidth} ${className}`} title={text}>
      {children}
    </span>
  );
}

export function StageBadge({ stage }: { stage?: string | null }) {
  const label = stage || "New";
  const isNew = label === "New";
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${isNew ? "border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] text-[var(--vbase-slate600)]" : "border-[var(--vbase-indigo)]/30 bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]"}`}
      title={`Pipeline stage: ${label}`}
    >
      {label}
    </span>
  );
}

/** Phone number with a country-code indicator.

 * Numbers that already carry an international prefix get a green "+" mark
 * in front of the visible digits; the prefix symbol itself is the contact
 * record's source of truth, never a guessed country. Numbers without a prefix
 * keep the amber "no code" marker that points at Data Quality.
 */
export function PhoneCell({ phone, maxWidth = "max-w-[160px]" }: { phone?: string | null; maxWidth?: string }) {
  if (!phone) return <span className="text-sm text-[var(--vbase-slate400)]">—</span>;
  const parsed = parsePhone(phone);
  const display = parsed?.display ?? phone;
  const hasPrefix = parsed && parsed.hasCountryCode;
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5 text-sm text-[var(--vbase-slate800)]">
      <IconPhone className="h-3.5 w-3.5 flex-shrink-0 text-[var(--vbase-slate500)]" />
      <span className={`block truncate ${maxWidth}`} title={display}>{display}</span>
      {hasPrefix ? (
        <span
          className="flex-shrink-0 rounded-full bg-[var(--vbase-green)]/10 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-[var(--vbase-green)]"
          title="Country code present"
        >
          +
        </span>
      ) : (
        <span
          className="flex-shrink-0 rounded-full bg-[var(--vbase-amber)]/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--vbase-amber)]"
          title="No country code — see Data Quality"
        >
          no code
        </span>
      )}
    </span>
  );
}
