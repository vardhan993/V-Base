import { useState, useEffect, useCallback } from "react";
import { IconMerge, IconCheck, IconAlertTriangle, IconUsers, IconBuilding2 } from "@/lib/icons";
import { api } from "@/lib/api";
import { toast } from "@/lib/store";

export function DuplicatesPage() {
  const [candidates, setCandidates] = useState<any[]>([]);
  const [, setLoading] = useState(false);
  const [status, setStatus] = useState("open");

  const fetchDuplicates = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<any>("/duplicates", { params: { status } });
      setCandidates(data.items || []);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, [status]);

  useEffect(() => { fetchDuplicates(); }, [fetchDuplicates, status]);

  const merge = async (id: number, keepId: number) => {
    await api.post(`/duplicates/${id}/merge`, { keep_record_id: keepId });
    toast("Merged", "success");
    fetchDuplicates();
  };

  const keepBoth = async (id: number) => {
    await api.post(`/duplicates/${id}/keep-both`);
    toast("Kept both", "success");
    fetchDuplicates();
  };

  const ignore = async (id: number) => {
    await api.post(`/duplicates/${id}/ignore`);
    toast("Ignored", "success");
    fetchDuplicates();
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Duplicates</h1>
        <div className="flex items-center gap-2">
          {["open", "resolved", "ignored"].map((s) => (
            <button key={s} onClick={() => setStatus(s)} className={`vbase-chip ${status === s ? "text-[var(--vbase-indigo)] bg-[var(--vbase-indigo)]/10" : ""}`}>{s.charAt(0).toUpperCase() + s.slice(1)}</button>
          ))}
        </div>
      </div>

      <div className="vbase-card overflow-hidden">
        <div className="border-b border-[var(--vbase-border)] px-4 py-3">
          <h3 className="font-semibold text-[var(--vbase-slate800)]">Duplicate candidates</h3>
          <p className="text-xs text-[var(--vbase-slate500)]">{candidates.length} found</p>
        </div>
        {candidates.map((c) => (
          <div key={c.id} className="flex flex-col gap-3 px-4 py-4 border-b border-[var(--vbase-border)]">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-md bg-[var(--vbase-bg-alt)]">
                  {c.entity_type === "contact" ? <IconUsers className="h-4 w-4 text-[var(--vbase-slate500)]" /> : <IconBuilding2 className="h-4 w-4 text-[var(--vbase-slate500)]" />}
                </div>
                <div>
                  <p className="font-medium text-[var(--vbase-slate800)]">{c.match_type} match · {Math.round(c.match_score * 100)}%</p>
                  <p className="text-xs text-[var(--vbase-slate500)]">{c.entity_type} · {c.status}</p>
                </div>
              </div>
              <span className={`vbase-chip ${c.status === "open" ? "bg-[var(--vbase-amber)]/10 text-[var(--vbase-amber)]" : c.status === "resolved" ? "bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]" : "bg-[var(--vbase-slate100)] text-[var(--vbase-slate500)]"}`}>{c.status}</span>
            </div>
            {c.record && c.match && (
              <div className="grid gap-3 md:grid-cols-2">
                <DetailCard label="Record" id={c.record.id} name={c.record.name || c.record.company_name} email={c.record.email || c.record.domain} type={c.entity_type} />
                <DetailCard label="Match" id={c.match.id} name={c.match.name || c.match.company_name} email={c.match.email || c.match.domain} type={c.entity_type} />
              </div>
            )}
            <div className="flex items-center gap-2">
              <button onClick={() => merge(c.id, c.record_id)} className="vbase-btn-primary flex items-center gap-1.5"><IconMerge className="h-4 w-4" /><span>Merge</span></button>
              <button onClick={() => keepBoth(c.id)} className="vbase-btn-secondary flex items-center gap-1.5"><IconCheck className="h-4 w-4" /><span>Keep both</span></button>
              <button onClick={() => ignore(c.id)} className="vbase-btn-ghost flex items-center gap-1.5"><IconAlertTriangle className="h-4 w-4" /><span>Ignore</span></button>
            </div>
          </div>
        ))}
        {!candidates.length && (
          <div className="px-4 py-12 text-center text-sm text-[var(--vbase-slate500)]">
            <IconAlertTriangle className="h-8 w-8 mx-auto mb-2 text-[var(--vbase-slate300)]" />
            No duplicate candidates
          </div>
        )}
      </div>
    </div>
  );
}

function DetailCard({ label, id, name, email, type }: any) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] p-3">
      <div className="mt-0.5 flex h-7 w-7 items-center justify-center rounded border border-[var(--vbase-border)] bg-[var(--vbase-bg)] text-[var(--vbase-slate500)]">
        {type === "contact" ? <IconUsers className="h-3.5 w-3.5" /> : <IconBuilding2 className="h-3.5 w-3.5" />}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-[var(--vbase-slate500)]">{label}</p>
        <p className="mt-0.5 font-medium text-[var(--vbase-slate800)]">{name}</p>
        {email && <p className="text-xs text-[var(--vbase-slate500)]">{email}</p>}
        <p className="text-xs text-[var(--vbase-slate400)]">ID: {id}</p>
      </div>
    </div>
  );
}
