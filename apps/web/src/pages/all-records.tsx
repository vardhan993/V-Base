import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { IconSearch, IconBuilding2, IconUsers } from "@/lib/icons";
import { api } from "@/lib/api";

export function AllRecordsPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const search = useCallback(async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await api.get<any>("/search/global", { params: { q: query, limit: 50 } });
      setResults(data);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, [query]);

  useEffect(() => {
    let cancelled = false;
    const t = setTimeout(() => { if (!cancelled) search(); }, 300);
    return () => { cancelled = true; clearTimeout(t); };
  }, [search]);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">All Records</h1>
      <div className="relative max-w-3xl">
        <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--vbase-slate400)]" />
        <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search across contacts, companies, emails, phones, LinkedIn…" className="vbase-input pl-9 h-10" />
      </div>

      {loading && !results && (
        <div className="flex h-40 items-center justify-center"><div className="h-6 w-48 rounded bg-[var(--vbase-slate200)]" /></div>
      )}

      {results && (
        <div className="flex flex-col gap-6">
          <div className="vbase-card overflow-hidden">
            <div className="border-b border-[var(--vbase-border)] px-4 py-3">
              <h3 className="font-semibold text-[var(--vbase-slate800)]">Results</h3>
              <p className="text-xs text-[var(--vbase-slate500)]">{results.total} matches</p>
            </div>
            <div className="divide-y divide-[var(--vbase-border)]">
              {results.companies?.map((c: any) => (
                <div key={`c-${c.id}`} className="flex items-center gap-3 px-4 py-3">
                  <div className="h-8 w-8 flex items-center justify-center rounded-md bg-[var(--vbase-bg-alt)] text-[var(--vbase-slate600)]"><IconBuilding2 className="h-4 w-4" /></div>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-[var(--vbase-slate900)]">{c.name}</p>
                    <p className="text-xs text-[var(--vbase-slate500)]">{c.subtitle}</p>
                  </div>
                  <span className="vbase-chip flex h-7 items-center px-2.5 py-0.5">Company</span>
                  <Link to={`/companies/${c.id}`} className="text-sm text-[var(--vbase-indigo)] hover:underline">Open</Link>
                </div>
              ))}
              {results.contacts?.map((c: any) => (
                <div key={`co-${c.id}`} className="flex items-center gap-3 px-4 py-3">
                  <div className="h-8 w-8 flex items-center justify-center rounded-md bg-[var(--vbase-bg-alt)] text-[var(--vbase-slate600)]"><IconUsers className="h-4 w-4" /></div>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-[var(--vbase-slate900)]">{c.name}</p>
                    <p className="text-xs text-[var(--vbase-slate500)]">{c.subtitle}</p>
                  </div>
                  <span className="vbase-chip flex h-7 items-center px-2.5 py-0.5">Contact</span>
                  <Link to={`/contacts/${c.id}`} className="text-sm text-[var(--vbase-indigo)] hover:underline">Open</Link>
                </div>
              ))}
              {(!results.companies?.length && !results.contacts?.length) && (
                <div className="px-4 py-8 text-center text-sm text-[var(--vbase-slate500)]">
                  No results for “{query}”
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {!query && !results && (
        <div className="flex flex-col items-center gap-3 py-16 text-center text-sm text-[var(--vbase-slate500)]">
          <IconSearch className="h-8 w-8" />
          Enter a search to find records across companies and contacts.
        </div>
      )}
    </div>
  );
}
