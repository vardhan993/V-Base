import { useState, useEffect, useCallback, type FormEvent } from "react";
import { api } from "@/lib/api";
import { toast } from "@/lib/store";
import {
  IconPhone,
  IconPlus,
  IconTrash2,
  IconMapPin,
  IconFileText,
  IconDownload,
} from "@/lib/icons";

/* ------------------------------------------------------------------ */
/* Calls                                                               */
/* ------------------------------------------------------------------ */

interface CallEntry {
  id: number;
  direction: string;
  outcome: string;
  duration_seconds?: number | null;
  phone_number?: string | null;
  notes?: string | null;
  created_at?: string | null;
}

const OUTCOME_META: Record<string, { label: string; cls: string }> = {
  connected: { label: "Connected", cls: "text-[var(--vbase-green)]" },
  voicemail: { label: "Voicemail", cls: "text-[var(--vbase-amber)]" },
  missed: { label: "Missed", cls: "text-[var(--vbase-red)]" },
  scheduled: { label: "Scheduled", cls: "text-[var(--vbase-cyan)]" },
};

export function CallsCard({ contactId, companyId }: { contactId?: number; companyId?: number }) {
  const [calls, setCalls] = useState<CallEntry[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [direction, setDirection] = useState("outbound");
  const [outcome, setOutcome] = useState("connected");
  const [duration, setDuration] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    const params: Record<string, string | number | boolean | undefined | null> = {};
    if (contactId) params.contact_id = contactId;
    if (companyId) params.company_id = companyId;
    try {
      const data = await api.get<{ items: CallEntry[]; outcome_counts: Record<string, number> }>("/calls", { params });
      setCalls(data.items);
      setCounts(data.outcome_counts || {});
    } catch {
      /* the card is secondary */
    }
  }, [contactId, companyId]);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post("/calls", {
        ...(contactId ? { contact_id: contactId } : {}),
        ...(companyId ? { company_id: companyId } : {}),
        direction,
        outcome,
        duration_seconds: duration ? Number(duration) * 60 : undefined,
        notes: notes || undefined,
      });
      setDuration("");
      setNotes("");
      toast("Call logged", "success");
      load();
    } catch (err: any) {
      toast(err?.data?.detail || "Could not log the call", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-3 text-xs">
        {Object.entries(OUTCOME_META).map(([key, meta]) => (
          <span key={key} className={meta.cls}>
            {meta.label}: <span className="font-semibold tnum">{counts[key] ?? 0}</span>
          </span>
        ))}
      </div>
      {calls.length ? (
        <ul className="space-y-1.5">
          {calls.map((c) => {
            const meta = OUTCOME_META[c.outcome] ?? { label: c.outcome, cls: "" };
            return (
              <li key={c.id} className="flex items-center gap-2 text-sm">
                <IconPhone
                  className={`h-3.5 w-3.5 flex-shrink-0 ${c.direction === "outbound" ? "rotate-[100deg]" : ""} text-[var(--vbase-slate500)]`}
                />
                <span className={`font-medium ${meta.cls}`}>{meta.label}</span>
                {c.duration_seconds ? (
                  <span className="tnum text-xs text-[var(--vbase-slate500)]">
                    {Math.floor(c.duration_seconds / 60)}m {c.duration_seconds % 60}s
                  </span>
                ) : null}
                {c.notes && <span className="min-w-0 flex-1 truncate text-[var(--vbase-slate600)]">— {c.notes}</span>}
                <span className="ml-auto flex-shrink-0 text-xs text-[var(--vbase-slate400)]">
                  {c.created_at ? new Date(c.created_at).toLocaleDateString() : ""}
                </span>
                <button
                  type="button"
                  aria-label="Delete call"
                  className="vbase-btn-icon-sm vbase-btn-danger-soft"
                  onClick={() => api.delete(`/calls/${c.id}`).then(load)}
                >
                  <IconTrash2 className="h-3.5 w-3.5" />
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-sm text-[var(--vbase-slate400)]">No calls logged yet.</p>
      )}

      <form onSubmit={submit} className="mt-3 flex flex-wrap items-center gap-2">
        <select value={direction} onChange={(e) => setDirection(e.target.value)} className="vbase-select h-8 w-auto text-sm">
          <option value="outbound">Outbound</option>
          <option value="inbound">Inbound</option>
        </select>
        <select value={outcome} onChange={(e) => setOutcome(e.target.value)} className="vbase-select h-8 w-auto text-sm">
          {Object.entries(OUTCOME_META).map(([key, meta]) => (
            <option key={key} value={key}>
              {meta.label}
            </option>
          ))}
        </select>
        <input
          type="number"
          min="0"
          value={duration}
          onChange={(e) => setDuration(e.target.value)}
          placeholder="Minutes"
          className="vbase-input h-8 w-24 text-sm"
          aria-label="Duration in minutes"
        />
        <input
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Notes…"
          className="vbase-input h-8 min-w-0 flex-1 text-sm"
        />
        <button type="submit" disabled={saving} className="vbase-btn-secondary vbase-btn-sm flex-shrink-0">
          <IconPlus className="h-3.5 w-3.5" />
          Log call
        </button>
      </form>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Notes                                                               */
/* ------------------------------------------------------------------ */

interface NoteEntry {
  id: number;
  body: string;
  pinned: boolean;
  author?: string | null;
  created_at?: string | null;
}

export function NotesCard({ contactId, companyId, leadId }: { contactId?: number; companyId?: number; leadId?: number }) {
  const [notes, setNotes] = useState<NoteEntry[]>([]);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    const params: Record<string, string | number | boolean | undefined | null> = {};
    if (contactId) params.contact_id = contactId;
    if (companyId) params.company_id = companyId;
    if (leadId) params.lead_id = leadId;
    try {
      const data = await api.get<{ items: NoteEntry[] }>("/notes", { params });
      setNotes(data.items);
    } catch {
      /* the card is secondary */
    }
  }, [contactId, companyId, leadId]);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!draft.trim()) return;
    setSaving(true);
    try {
      await api.post("/notes", {
        body: draft.trim(),
        ...(contactId ? { contact_id: contactId } : {}),
        ...(companyId ? { company_id: companyId } : {}),
        ...(leadId ? { lead_id: leadId } : {}),
      });
      setDraft("");
      load();
    } catch (err: any) {
      toast(err?.data?.detail || "Could not save the note", "error");
    } finally {
      setSaving(false);
    }
  };

  const togglePin = async (note: NoteEntry) => {
    try {
      await api.patch(`/notes/${note.id}`, { pinned: !note.pinned });
      load();
    } catch {
      toast("Could not update the note", "error");
    }
  };

  return (
    <div>
      {notes.length ? (
        <ul className="space-y-2">
          {notes.map((n) => (
            <li key={n.id} className="rounded-lg border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] p-3">
              <div className="flex items-start gap-2">
                <IconFileText className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-[var(--vbase-slate400)]" />
                <p className="min-w-0 flex-1 whitespace-pre-wrap text-sm text-[var(--vbase-slate700)]">{n.body}</p>
                <button
                  type="button"
                  aria-label={n.pinned ? "Unpin note" : "Pin note"}
                  className={`flex-shrink-0 rounded p-1 transition-colors ${
                    n.pinned
                      ? "text-[var(--vbase-amber)]"
                      : "text-[var(--vbase-slate400)] hover:text-[var(--vbase-slate700)]"
                  }`}
                  onClick={() => togglePin(n)}
                >
                  {n.pinned ? <IconMapPin className="h-3.5 w-3.5" /> : <IconMapPin className="h-3.5 w-3.5 opacity-40" />}
                </button>
                <button
                  type="button"
                  aria-label="Delete note"
                  className="vbase-btn-icon-sm vbase-btn-danger-soft flex-shrink-0"
                  onClick={() => api.delete(`/notes/${n.id}`).then(load)}
                >
                  <IconTrash2 className="h-3.5 w-3.5" />
                </button>
              </div>
              <p className="mt-1.5 text-[11px] text-[var(--vbase-slate400)]">
                {n.author ? `${n.author} · ` : ""}
                {n.created_at ? new Date(n.created_at).toLocaleString() : ""}
                {n.pinned ? " · 📌" : ""}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-[var(--vbase-slate400)]">No notes yet.</p>
      )}
      <form onSubmit={submit} className="mt-3 flex gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add a note…"
          className="vbase-input h-8 text-sm"
        />
        <button type="submit" disabled={saving || !draft.trim()} className="vbase-btn-secondary vbase-btn-sm flex-shrink-0">
          <IconPlus className="h-3.5 w-3.5" />
          Add
        </button>
      </form>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Unified timeline                                                    */
/* ------------------------------------------------------------------ */

interface TimelineEntry {
  kind: "call" | "note";
  id: number;
  direction?: string;
  outcome?: string;
  duration_seconds?: number | null;
  body?: string;
  author?: string | null;
  created_at?: string | null;
}

export function TimelineCard({ contactId, companyId }: { contactId?: number; companyId?: number }) {
  const [items, setItems] = useState<TimelineEntry[]>([]);

  useEffect(() => {
    const params: Record<string, string | number | boolean | undefined | null> = {};
    if (contactId) params.contact_id = contactId;
    if (companyId) params.company_id = companyId;
    api
      .get<{ items: TimelineEntry[] }>("/timeline", { params })
      .then((d) => setItems(d.items))
      .catch(() => setItems([]));
  }, [contactId, companyId]);

  return (
    <div>
      {items.length ? (
        <ol className="relative space-y-3 border-l border-[var(--vbase-border)] pl-4">
          {items.map((e) => (
            <li key={`${e.kind}-${e.id}`}>
              <span
                className={`absolute -left-[7px] mt-1 flex h-3.5 w-3.5 items-center justify-center rounded-full border-2 border-[var(--vbase-bg)] ${
                  e.kind === "call" ? "bg-[var(--vbase-cyan)]" : "bg-[var(--vbase-indigo)]"
                }`}
              />
              <div className="flex items-baseline gap-2">
                {e.kind === "call" ? (
                  <>
                    <span className="text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Call · {e.outcome}
                    </span>
                    {e.duration_seconds ? (
                      <span className="tnum text-xs text-[var(--vbase-slate400)]">
                        {Math.floor(e.duration_seconds / 60)}m {e.duration_seconds % 60}s
                      </span>
                    ) : null}
                    {e.direction && <IconPhone className="h-3 w-3 text-[var(--vbase-slate400)]" />}
                  </>
                ) : (
                  <>
                    <span className="text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Note
                    </span>
                    {e.author && <span className="text-xs text-[var(--vbase-slate400)]">by {e.author}</span>}
                  </>
                )}
                <span className="ml-auto text-xs text-[var(--vbase-slate400)]">
                  {e.created_at ? new Date(e.created_at).toLocaleString() : ""}
                </span>
              </div>
              {e.body && <p className="mt-0.5 whitespace-pre-wrap text-sm text-[var(--vbase-slate700)]">{e.body}</p>}
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-[var(--vbase-slate400)]">
          Nothing yet — calls and notes will appear here.
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Export + vCard buttons                                              */
/* ------------------------------------------------------------------ */

function downloadBlob(url: string) {
  // The API returns Content-Disposition; use a plain link navigation so the
  // browser handles the file name. Cookies ride along automatically.
  const a = document.createElement("a");
  a.href = url;
  a.rel = "noopener";
  a.click();
}

export function ExportButtons({
  endpoint,
  ids,
  filenameLabel,
}: {
  endpoint: "contacts" | "companies";
  ids: number[];
  filenameLabel: string;
}) {
  const query = encodeURIComponent(ids.join(","));

  return (
    <div className="flex flex-wrap gap-2">
      <a
        href={`/api/v1/exports/${endpoint}?ids=${query}&format=csv`}
        className="vbase-btn-secondary vbase-btn-sm"
        onClick={(e) => {
          e.preventDefault();
          downloadBlob(`/api/v1/exports/${endpoint}?ids=${query}&format=csv`);
        }}
      >
        <IconDownload className="h-3.5 w-3.5" />
        CSV
      </a>
      <a
        href={`/api/v1/exports/${endpoint}?ids=${query}&format=xlsx`}
        className="vbase-btn-secondary vbase-btn-sm"
        onClick={(e) => {
          e.preventDefault();
          downloadBlob(`/api/v1/exports/${endpoint}?ids=${query}&format=xlsx`);
        }}
      >
        <IconDownload className="h-3.5 w-3.5" />
        Excel
      </a>
      <span className="self-center text-xs text-[var(--vbase-slate400)]">{filenameLabel}</span>
    </div>
  );
}

export function VCardButton({ contactId }: { contactId: number }) {
  return (
    <a
      href={`/api/v1/contacts/${contactId}/vcard`}
      className="vbase-btn-ghost flex items-center gap-1.5 text-sm"
      onClick={(e) => {
        e.preventDefault();
        downloadBlob(`/api/v1/contacts/${contactId}/vcard`);
      }}
    >
      <IconDownload className="h-4 w-4" />
      vCard
    </a>
  );
}
