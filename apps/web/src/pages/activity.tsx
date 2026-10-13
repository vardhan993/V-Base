import { useState, useEffect, useCallback } from "react";
import { IconRefreshCcw, IconX } from "@/lib/icons";
import { api } from "@/lib/api";
import { ActivityLogEntry } from "@/lib/types";

export function ActivityPage() {
  const [logs, setLogs] = useState<ActivityLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [, setLoading] = useState(false);
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<{ items: ActivityLogEntry[]; total: number }>("/activity", { params: { page, page_size: pageSize, action: action || undefined, entity_type: entityType || undefined } });
      setLogs(data.items);
      setTotal(data.total);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, [page, pageSize, action, entityType]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  const clearFilters = () => { setAction(""); setEntityType(""); setPage(1); };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Activity</h1>
        <div className="flex items-center gap-2">
          <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page <= 1} className="vbase-btn-ghost flex items-center gap-1"><IconRefreshCcw className="h-4 w-4" /><span>Previous</span></button>
          <span className="text-sm text-[var(--vbase-slate500)]">{page} / {Math.max(1, Math.ceil(total / pageSize))}</span>
          <button onClick={() => setPage(Math.min(Math.ceil(total / pageSize), page + 1))} disabled={page >= Math.ceil(total / pageSize)} className="vbase-btn-ghost flex items-center gap-1"><span>Next</span><IconRefreshCcw className="h-4 w-4 -scale-x-100" /></button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <select value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }} className="vbase-select max-w-[140px]">
          <option value="">All actions</option>
          {["login", "logout", "signup", "import", "create", "update", "delete", "merge", "export"].map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <select value={entityType} onChange={(e) => { setEntityType(e.target.value); setPage(1); }} className="vbase-select max-w-[140px]">
          <option value="">All entities</option>
          {["companies", "contacts", "users", "lists", "tags", "import_jobs"].map((e) => (
            <option key={e} value={e}>{e}</option>
          ))}
        </select>
        {action || entityType ? (
          <button onClick={clearFilters} className="vbase-btn-ghost flex items-center gap-1.5 text-sm"><IconX className="h-3.5 w-3.5" /><span>Clear filters</span></button>
        ) : null}
      </div>

      <div className="vbase-card overflow-hidden">
        <div className="border-b border-[var(--vbase-border)] px-4 py-3">
          <h3 className="font-semibold text-[var(--vbase-slate800)]">Recent activity</h3>
          <p className="text-xs text-[var(--vbase-slate500)]">{total} events</p>
        </div>
        <div className="divide-y divide-[var(--vbase-border)]">
          {logs.map((log) => (
            <div key={log.id} className="flex items-start gap-3 px-4 py-3">
              <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-md bg-[var(--vbase-bg-alt)] text-[var(--vbase-indigo)]">
                <span className="text-xs font-semibold">{log.action.charAt(0).toUpperCase()}</span>
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-[var(--vbase-slate800)]">{log.description || log.action}</p>
                <p className="text-xs text-[var(--vbase-slate500)]">{log.entity_type} · {log.entity_id} · {log.user_id ? "user " + log.user_id : "system"}</p>
                <p className="text-xs text-[var(--vbase-slate400)] mt-1">{log.created_at ? new Date(log.created_at).toLocaleString() : ""}</p>
              </div>
              <span className="text-xs text-[var(--vbase-slate500)]">{log.created_at ? new Date(log.created_at).toLocaleTimeString() : ""}</span>
            </div>
          ))}
          {!logs.length && (
            <div className="px-4 py-12 text-center text-sm text-[var(--vbase-slate500)]">
              No activity yet
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
