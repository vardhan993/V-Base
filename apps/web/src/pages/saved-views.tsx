import { useState, useEffect, useCallback } from "react";
import { IconPlus, IconTrash2, IconTable2, IconCopy, IconExternalLink } from "@/lib/icons";
import { api } from "@/lib/api";
import { toast } from "@/lib/store";

interface SavedView {
  id: number;
  name: string;
  entity: string;
  columns: string[];
  sort: any[];
  filters: any[];
  updated_at?: string | null;
}

export function SavedViewsPage() {
  const [views, setViews] = useState<SavedView[]>([]);
  const [, setLoading] = useState(false);
  const [entity, setEntity] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [newEntity, setNewEntity] = useState("contacts");

  const fetchViews = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<SavedView[]>("/views", { params: entity ? { entity } : {} });
      setViews(data);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, [entity]);

  useEffect(() => { fetchViews(); }, [fetchViews]);

  const create = async () => {
    if (!name.trim()) { toast("Name is required", "error"); return; }
    try {
      await api.post("/views", { name: name.trim(), entity: newEntity, columns: [], sort: [], filters: [] });
      toast("Saved view created", "success");
      setName("");
      setCreateOpen(false);
      fetchViews();
    } catch (e: any) { toast(e?.data?.detail || e?.message || "Create failed", "error"); }
  };

  const duplicate = async (id: number) => {
    try {
      await api.post(`/views/${id}/duplicate`);
      toast("View duplicated", "success");
      fetchViews();
    } catch (e: any) { toast(e?.data?.detail || e?.message || "Duplicate failed", "error"); }
  };

  const remove = async (id: number) => {
    if (!window.confirm("Delete this saved view?")) return;
    try {
      await api.delete(`/views/${id}`);
      toast("Saved view deleted", "success");
      fetchViews();
    } catch (e: any) { toast(e?.data?.detail || e?.message || "Delete failed", "error"); }
  };

  const apply = (v: SavedView) => {
    window.location.hash = v.entity === "companies" ? "/companies" : "/contacts";
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Saved Views</h1>
        <div className="flex items-center gap-2">
          <select value={entity} onChange={(e) => setEntity(e.target.value)} className="vbase-select max-w-[160px]">
            <option value="">All entities</option>
            <option value="contacts">Contacts</option>
            <option value="companies">Companies</option>
          </select>
          <button onClick={() => setCreateOpen(true)} className="vbase-btn-primary flex items-center gap-1.5"><IconPlus className="h-4 w-4" /><span>New view</span></button>
        </div>
      </div>

      {createOpen && (
        <div className="vbase-card p-6">
          <h3 className="mb-4 font-semibold text-[var(--vbase-slate800)]">Create saved view</h3>
          <div className="space-y-4">
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="View name" className="vbase-input" />
            <select value={newEntity} onChange={(e) => setNewEntity(e.target.value)} className="vbase-select">
              <option value="contacts">Contacts</option>
              <option value="companies">Companies</option>
            </select>
            <div className="flex items-center justify-end gap-2">
              <button onClick={() => setCreateOpen(false)} className="vbase-btn-ghost">Cancel</button>
              <button onClick={create} className="vbase-btn-primary">Save</button>
            </div>
          </div>
        </div>
      )}

      <div className="vbase-card overflow-hidden">
        <div className="border-b border-[var(--vbase-border)] px-4 py-3">
          <h3 className="font-semibold text-[var(--vbase-slate800)]">Views remember table layouts for later</h3>
        </div>
        {views.map((v) => (
          <div key={v.id} className="flex items-center gap-3 px-4 py-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-[var(--vbase-bg-alt)]">
              <IconTable2 className="h-4 w-4 text-[var(--vbase-slate500)]" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-medium text-[var(--vbase-slate800)]">{v.name}</p>
              <p className="text-xs text-[var(--vbase-slate500)]">{v.entity} · {(v.columns || []).length} columns · {(v.filters || []).length} filters</p>
            </div>
            <button onClick={() => apply(v)} className="vbase-btn-ghost flex items-center gap-1"><IconExternalLink className="h-4 w-4" /><span>Open</span></button>
            <button onClick={() => duplicate(v.id)} className="vbase-btn-ghost flex items-center gap-1"><IconCopy className="h-4 w-4" /><span>Duplicate</span></button>
            <button onClick={() => remove(v.id)} className="vbase-btn-danger flex items-center gap-1"><IconTrash2 className="h-4 w-4" /><span>Delete</span></button>
          </div>
        ))}
        {!views.length && (
          <div className="px-4 py-12 text-center text-sm text-[var(--vbase-slate500)]">
            <IconTable2 className="h-8 w-8 mx-auto mb-2 text-[var(--vbase-slate300)]" />
            No saved views yet
          </div>
        )}
      </div>
    </div>
  );
}
