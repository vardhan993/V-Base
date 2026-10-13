import { useState, useEffect } from "react";
import { IconAlertTriangle, IconCheck } from "@/lib/icons";
import { api } from "@/lib/api";
import { QualitySummary } from "@/lib/types";

export function DataQualityPage() {
  const [summary, setSummary] = useState<QualitySummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await api.get<QualitySummary>("/quality/summary");
        if (!cancelled) setSummary(data);
      } catch (e) { console.error(e); } finally { if (!cancelled) setLoading(false); }
    };
    load();
    return () => { cancelled = true; };
  }, []);

  const overall = summary ? Math.round((summary.contacts.with_email / Math.max(1, summary.contacts.total)) * 50 + (summary.contacts.with_phone / Math.max(1, summary.contacts.total)) * 20 + (summary.contacts.with_linkedin / Math.max(1, summary.contacts.total)) * 20 + (summary.contacts.with_company / Math.max(1, summary.contacts.total)) * 10) : 0;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Data Quality</h1>
      <p className="text-sm text-[var(--vbase-slate500)]">A completeness indicator, not proof that contact data is accurate.</p>

      {loading ? (
        <div className="flex h-64 items-center justify-center"><div className="h-6 w-48 rounded bg-[var(--vbase-slate200)]" /></div>
      ) : summary ? (
        <>
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            <QualityCard label="Overall quality" value={overall} max={100} color={overall >= 70 ? "var(--vbase-green)" : overall >= 40 ? "var(--vbase-amber)" : "var(--vbase-red)"} />
            <QualityCard label="Contacts with email" value={summary.contacts.with_email} max={summary.contacts.total} />
            <QualityCard label="Contacts with phone" value={summary.contacts.with_phone} max={summary.contacts.total} />
            <QualityCard label="Contacts with LinkedIn" value={summary.contacts.with_linkedin} max={summary.contacts.total} />
            <QualityCard label="Contacts with company" value={summary.contacts.with_company} max={summary.contacts.total} />
            <QualityCard label="Valid emails" value={summary.contacts.with_email - summary.contacts.invalid_email} max={summary.contacts.total} color="var(--vbase-green)" />
            <QualityCard label="Stale contacts" value={summary.contacts.stale} max={summary.contacts.total} color="var(--vbase-amber)" />
            <QualityCard label="Companies missing domain" value={summary.companies.missing_domain} max={summary.companies.total} color="var(--vbase-amber)" />
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            <DetailCard title="Missing data" icon={<IconAlertTriangle className="h-4 w-4" />}>
              <ul className="space-y-3">
                <li className="flex items-center justify-between rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-4 py-3">
                  <span className="text-sm text-[var(--vbase-slate800)]">Missing emails</span>
                  <span className="text-sm font-medium text-[var(--vbase-slate600)]">{summary.contacts.with_email} / {summary.contacts.total}</span>
                </li>
                <li className="flex items-center justify-between rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-4 py-3">
                  <span className="text-sm text-[var(--vbase-slate800)]">Missing phone</span>
                  <span className="text-sm font-medium text-[var(--vbase-slate600)]">{summary.contacts.with_phone} / {summary.contacts.total}</span>
                </li>
                <li className="flex items-center justify-between rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-4 py-3">
                  <span className="text-sm text-[var(--vbase-slate800)]">Missing LinkedIn</span>
                  <span className="text-sm font-medium text-[var(--vbase-slate600)]">{summary.contacts.with_linkedin} / {summary.contacts.total}</span>
                </li>
                <li className="flex items-center justify-between rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-4 py-3">
                  <span className="text-sm text-[var(--vbase-slate800)]">Missing company</span>
                  <span className="text-sm font-medium text-[var(--vbase-slate600)]">{summary.contacts.with_company} / {summary.contacts.total}</span>
                </li>
                <li className="flex items-center justify-between rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-4 py-3">
                  <span className="text-sm text-[var(--vbase-slate800)]">Missing domain (companies)</span>
                  <span className="text-sm font-medium text-[var(--vbase-slate600)]">{summary.companies.missing_domain} / {summary.companies.total}</span>
                </li>
              </ul>
            </DetailCard>

            <DetailCard title="Invalid data" icon={<IconAlertTriangle className="h-4 w-4 text-[var(--vbase-red)]" />}>
              <ul className="space-y-3">
                <li className="flex items-center justify-between rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-4 py-3">
                  <span className="text-sm text-[var(--vbase-slate800)]">Invalid email format</span>
                  <span className="text-sm font-medium text-[var(--vbase-red)]">{summary.contacts.invalid_email}</span>
                </li>
                <li className="flex items-center justify-between rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-4 py-3">
                  <span className="text-sm text-[var(--vbase-slate800)]">Phones without a country code</span>
                  <span className="text-sm font-medium text-[var(--vbase-amber)]">{summary.contacts.phone_missing_country_code}</span>
                </li>
                <li className="flex items-center justify-between rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-4 py-3">
                  <span className="text-sm text-[var(--vbase-slate800)]">Companies missing website</span>
                  <span className="text-sm font-medium text-[var(--vbase-slate600)]">{summary.companies.missing_website} / {summary.companies.total}</span>
                </li>
                <li className="flex items-center justify-between rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-4 py-3">
                  <span className="text-sm text-[var(--vbase-slate800)]">Companies missing LinkedIn</span>
                  <span className="text-sm font-medium text-[var(--vbase-slate600)]">{summary.companies.missing_linkedin} / {summary.companies.total}</span>
                </li>
              </ul>
            </DetailCard>
          </div>

          <div className="vbase-card p-5">
            <h3 className="mb-2 text-base font-semibold text-[var(--vbase-slate800)]">About data quality score</h3>
            <p className="text-sm text-[var(--vbase-slate600)]">
              The score rewards completeness: email present +25, phone +20, LinkedIn +20, company linked +15, job title +10, recent verification +10. It is a completeness indicator, not proof that contact data is accurate or current. Always verify critical contacts through LinkedIn or other sources.
            </p>
          </div>
        </>
      ) : (
        <div className="flex flex-col items-center gap-3 py-16 text-center text-sm text-[var(--vbase-slate500)]">
          <IconCheck className="h-8 w-8" />
          No data to evaluate
        </div>
      )}
    </div>
  );
}

function QualityCard({ label, value, max, color }: any) {
  const pct = max ? Math.round((value / max) * 100) : 0;
  return (
    <div className="vbase-card p-4">
      <p className="text-xs text-[var(--vbase-slate500)] uppercase tracking-wider">{label}</p>
      <div className="mt-2 flex items-baseline gap-2">
        <p className="text-2xl font-semibold text-[var(--vbase-slate900)]">{value}</p>
        {max != null && <p className="text-sm text-[var(--vbase-slate500)]">/ {max}</p>}
      </div>
      <div className="mt-3 h-1.5 w-full rounded-full bg-[var(--vbase-slate200)]">
        <div className={`h-full rounded-full ${color ? `bg-[${color}]` : "bg-[var(--vbase-indigo)]"}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function DetailCard({ title, icon, children }: any) {
  return (
    <div className="vbase-card p-5">
      <h3 className="mb-4 flex items-center gap-2 font-semibold text-[var(--vbase-slate800)]">{icon} {title}</h3>
      {children}
    </div>
  );
}
