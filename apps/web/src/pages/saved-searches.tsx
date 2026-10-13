import { useState, useEffect, useCallback } from "react";
import { IconPlus, IconTrash2, IconSearch, IconStar } from "@/lib/icons";
import { api } from "@/lib/api";
import { SavedSearch } from "@/lib/types";
import { toast } from "@/lib/store";

export function SavedSearchesPage() {
  const [searches, setSearches] = useState<SavedSearch[]>([]);
  const [, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [query, setQuery] = useState("");

  const fetchSearches = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<SavedSearch[]>("/search/recent");
      setSearches(data);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchSearches(); }, [fetchSearches]);

  const create = async () => {
    if (!name.trim()) { toast("Name is required", "error"); return; }
    await api.post("/search/saved", { name: name.trim(), query: query.trim() || undefined, scope: "all" });
    toast("Saved search created", "success");
    setName("");
    setQuery("");
    setCreateOpen(false);
    fetchSearches();
  };

  const remove = async (id: number) => {
    await api.delete(`/search/saved/${id}`);
    toast("Saved search deleted", "success");
    fetchSearches();
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Saved Searches</h1>
        <button onClick={() => setCreateOpen(true)} className="vbase-btn-primary flex items-center gap-1.5"><IconPlus className="h-4 w-4" /><span>Save search</span></button>
      </div>

      {createOpen && (
        <div className="vbase-card p-6">
          <h3 className="mb-4 font-semibold text-[var(--vbase-slate800)]">Save current search</h3>
          <div className="space-y-4">
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Search name" className="vbase-input" />
            <input type="text" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search query (optional)" className="vbase-input" />
            <div className="flex items-center justify-end gap-2">
              <button onClick={() => setCreateOpen(false)} className="vbase-btn-ghost">Cancel</button>
              <button onClick={create} className="vbase-btn-primary">Save</button>
            </div>
          </div>
        </div>
      )}

      <div className="vbase-card overflow-hidden">
        <div className="border-b border-[var(--vbase-border)] px-4 py-3">
          <h3 className="font-semibold text-[var(--vbase-slate800)]">Saved searches</h3>
        </div>
        {searches.map((s) => (
          <div key={s.id} className="flex items-center gap-3 px-4 py-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-[var(--vbase-bg-alt)]">
              <IconSearch className="h-4 w-4 text-[var(--vbase-slate500)]" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-medium text-[var(--vbase-slate800)]">{s.name}</p>
              {s.query && <p className="text-xs text-[var(--vbase-slate500)]">{s.query}</p>}
            </div>
            <button onClick={() => window.location.hash = `/search?q=${encodeURIComponent(s.query || "")}`} className="vbase-btn-ghost flex items-center gap-1"><IconStar className="h-4 w-4" /><span>Use</span></button>
            <button onClick={() => remove(s.id)} className="vbase-btn-danger flex items-center gap-1"><IconTrash2 className="h-4 w-4" /><span>Delete</span></button>
          </div>
        ))}
        {!searches.length && (
          <div className="px-4 py-12 text-center text-sm text-[var(--vbase-slate500)]">
            <IconSearch className="h-8 w-8 mx-auto mb-2 text-[var(--vbase-slate300)]" />
            No saved searches yet
          </div>
        )}
      </div>
    </div>
  );
}
