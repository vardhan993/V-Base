import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { IconTable2, IconPhone, IconMail, IconCheckCircle2 } from "@/lib/icons";
import { api } from "@/lib/api";
import { Contact } from "@/lib/types";
import { ContactAvatar, StageBadge, PhoneCell } from "@/components/crm";
import { CRM_STAGES } from "@/lib/crm";
import { toast } from "@/lib/store";

interface PipelineSummary {
  stages: { stage: string; count: number }[];
  open_tasks: number;
  overdue_tasks: number;
}

/** CRM pipeline: every contact in a funnel column by lifecycle stage.
 *
 * Cards show the reach-out essentials (phone with country-code state, email,
 * company) and move between stages with one select — no drag libraries, no
 * lost updates: a failed move rolls the select back and toasts the error.
 */
export function PipelinePage() {
  const [summary, setSummary] = useState<PipelineSummary | null>(null);
  const [columns, setColumns] = useState<Record<string, Contact[]>>({});
  const [loading, setLoading] = useState(true);
  const [moving, setMoving] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, ...lists] = await Promise.all([
        api.get<PipelineSummary>("/analytics/pipeline"),
        ...CRM_STAGES.map((stage) =>
          api.get<{ items: Contact[] }>("/contacts", { params: { stage, page_size: 50 } })
        ),
      ]);
      setSummary(s);
      const next: Record<string, Contact[]> = {};
      CRM_STAGES.forEach((stage, i) => {
        next[stage] = lists[i].items;
      });
      setColumns(next);
    } catch (e: any) {
      toast(e?.data?.detail || "Could not load the pipeline", "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const move = async (contact: Contact, stage: string) => {
    if (contact.stage === stage || moving !== null) return;
    setMoving(contact.id);
    const prev = columns;
    setColumns((cols) => {
      const next = { ...cols };
      next[contact.stage || "New"] = (next[contact.stage || "New"] || []).filter((c) => c.id !== contact.id);
      next[stage] = [{ ...contact, stage }, ...(next[stage] || [])];
      return next;
    });
    try {
      await api.patch(`/contacts/${contact.id}`, { stage });
      toast(`Moved to ${stage}`, "success");
    } catch (e: any) {
      setColumns(prev);
      toast(e?.data?.detail || "Move failed", "error");
    } finally {
      setMoving(null);
      load();
    }
  };

  if (loading && !summary) {
    return (
      <div className="flex h-64 flex-col gap-4">
        <div className="h-8 w-48 rounded-md bg-[var(--vbase-slate200)]" />
        <div className="grid gap-4 md:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-64 rounded-lg bg-[var(--vbase-slate200)]/60" />
          ))}
        </div>
      </div>
    );
  }

  const counts = new Map((summary?.stages || []).map((s) => [s.stage, s.count]));

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]">
            <IconTable2 className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Pipeline</h1>
            <p className="text-sm text-[var(--vbase-slate500)]">
              {(summary?.open_tasks ?? 0)} open follow-ups
              {(summary?.overdue_tasks ?? 0) > 0 && (
                <span className="text-[var(--vbase-red)]"> · {summary?.overdue_tasks} overdue</span>
              )}{" "}
              · <Link to="/tasks" className="text-[var(--vbase-indigo)] hover:underline">Open tasks</Link>
            </p>
          </div>
        </div>
        <Link to="/contacts" className="vbase-btn-secondary flex items-center gap-1.5">
          <span>All contacts</span>
        </Link>
      </div>

      <div className="grid flex-1 auto-rows-min gap-4 overflow-x-auto pb-4 md:grid-cols-3 xl:grid-cols-6">
        {CRM_STAGES.map((stage) => (
          <section key={stage} className="flex min-w-[240px] flex-col rounded-lg border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)]/50">
            <header className="flex items-center justify-between gap-2 px-3 py-2.5">
              <StageBadge stage={stage} />
              <span className="text-xs font-medium text-[var(--vbase-slate500)]">{counts.get(stage) ?? 0}</span>
            </header>
            <div className="flex max-h-[calc(100vh-320px)] flex-col gap-2 overflow-y-auto px-2 pb-2">
              {(columns[stage] || []).map((contact) => (
                <PipelineCard key={contact.id} contact={contact} disabled={moving !== null} onMove={move} />
              ))}
              {(columns[stage] || []).length === 0 && (
                <p className="px-2 py-6 text-center text-xs text-[var(--vbase-slate400)]">No contacts here yet</p>
              )}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

function PipelineCard({
  contact,
  disabled,
  onMove,
}: {
  contact: Contact;
  disabled: boolean;
  onMove: (contact: Contact, stage: string) => void;
}) {
  const name = contact.display_name || contact.full_name || contact.email || "Contact";
  return (
    <article className="rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg)] p-3 shadow-sm">
      <div className="flex items-center gap-2 min-w-0">
        <ContactAvatar name={name} size={28} />
        <Link
          to={`/contacts/${contact.id}`}
          title={name}
          className="block min-w-0 flex-1 truncate text-sm font-medium text-[var(--vbase-slate900)] hover:text-[var(--vbase-indigo)]"
        >
          {name}
        </Link>
      </div>
      {(contact.job_title || contact.company_name) && (
        <p className="mt-1.5 truncate text-xs text-[var(--vbase-slate500)]" title={[contact.job_title, contact.company_name].filter(Boolean).join(" · ")}>
          {[contact.job_title, contact.company_name].filter(Boolean).join(" · ")}
        </p>
      )}
      <div className="mt-2 space-y-1">
        {contact.phone && <PhoneCell phone={contact.phone} maxWidth="max-w-full" />}
        {contact.email && (
          <span className="flex min-w-0 items-center gap-1.5 text-xs text-[var(--vbase-slate600)]">
            <IconMail className="h-3 w-3 flex-shrink-0 text-[var(--vbase-slate400)]" />
            <span className="block truncate" title={contact.email}>
              {contact.email}
            </span>
          </span>
        )}
        {!contact.phone && !contact.email && (
          <span className="flex items-center gap-1 text-xs text-[var(--vbase-slate400)]">
            <IconPhone className="h-3 w-3" /> No reach-out details
          </span>
        )}
      </div>
      <label className="mt-2.5 flex items-center gap-1.5 text-xs text-[var(--vbase-slate500)]">
        <IconCheckCircle2 className="h-3.5 w-3.5 flex-shrink-0" />
        <select
          value={contact.stage || "New"}
          disabled={disabled}
          onChange={(e) => onMove(contact, e.target.value)}
          aria-label={`Move ${name} to stage`}
          className="vbase-select h-7 min-w-0 flex-1 text-xs"
        >
          {CRM_STAGES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
    </article>
  );
}
