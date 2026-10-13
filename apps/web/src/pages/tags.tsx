import { useCallback, useEffect, useMemo, useState } from "react";
import {
  IconTag,
  IconPlus,
  IconEdit,
  IconTrash2,
  IconSearch,
  IconLoader2,
  IconCheck,
  IconX,
  IconAlertCircle,
  IconClipboardList,
} from "@/lib/icons";
import { api } from "@/lib/api";
import { toast } from "@/lib/store";

interface Tag {
  id: number;
  name: string;
  color: string | null;
  kind: string | null;
  contact_count: number;
  company_count: number;
}

/** A small, opinionated palette so tags stay visually consistent. */
const PALETTE = [
  "#4f46e5",
  "#0ea5e9",
  "#059669",
  "#d97706",
  "#dc2626",
  "#db2777",
  "#7c3aed",
  "#475569",
];

const KINDS = ["general", "industry", "technology", "intent", "source", "status"];

function initials(name: string) {
  return name.trim().slice(0, 2).toUpperCase();
}

export function TagsPage() {
  const [tags, setTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [kindFilter, setKindFilter] = useState("");

  const [editing, setEditing] = useState<Tag | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [color, setColor] = useState(PALETTE[0]);
  const [kind, setKind] = useState("general");
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<Tag | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [applyOpen, setApplyOpen] = useState(false);
  const [applyTagId, setApplyTagId] = useState<number | "">("");
  const [applyEntity, setApplyEntity] = useState<"contact" | "company">("contact");
  const [applyIds, setApplyIds] = useState("");
  const [applying, setApplying] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.get<Tag[]>("/tags");
      setTags(data || []);
    } catch (e: any) {
      setError(e?.data?.detail || e?.message || "Could not load tags");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return tags.filter((t) => {
      if (q && !t.name.toLowerCase().includes(q)) return false;
      if (kindFilter && (t.kind || "general") !== kindFilter) return false;
      return true;
    });
  }, [tags, query, kindFilter]);

  const totals = useMemo(() => {
    const contacts = tags.reduce((sum, t) => sum + t.contact_count, 0);
    const companies = tags.reduce((sum, t) => sum + t.company_count, 0);
    const unused = tags.filter((t) => t.contact_count + t.company_count === 0).length;
    return { contacts, companies, unused };
  }, [tags]);

  const resetForm = () => {
    setName("");
    setColor(PALETTE[0]);
    setKind("general");
    setEditing(null);
    setCreating(false);
  };

  const openEdit = (tag: Tag) => {
    setEditing(tag);
    setCreating(false);
    setName(tag.name);
    setColor(tag.color || PALETTE[0]);
    setKind(tag.kind || "general");
  };

  const openCreate = () => {
    resetForm();
    setCreating(true);
  };

  const save = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      toast("Tag name is required", "error");
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await api.patch(`/tags/${editing.id}`, { name: trimmed, color, kind });
        toast(`Tag “${trimmed}” updated`, "success");
      } else {
        await api.post("/tags", { name: trimmed, color, kind });
        toast(`Tag “${trimmed}” created`, "success");
      }
      resetForm();
      await load();
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Save failed", "error");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (tag: Tag) => {
    setDeleting(true);
    try {
      await api.delete(`/tags/${tag.id}`);
      toast(`Tag “${tag.name}” deleted`, "success");
      setConfirmDelete(null);
      await load();
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Delete failed", "error");
    } finally {
      setDeleting(false);
    }
  };

  const parseIds = () =>
    applyIds
      .split(/[\s,;]+/)
      .map((v) => Number(v.trim()))
      .filter((v) => Number.isFinite(v) && v > 0);

  const applyTag = async (mode: "apply" | "remove") => {
    if (!applyTagId) {
      toast("Choose a tag first", "error");
      return;
    }
    const ids = parseIds();
    if (!ids.length) {
      toast("Enter at least one record id", "error");
      return;
    }
    setApplying(true);
    try {
      const body: Record<string, unknown> =
        applyEntity === "contact" ? { tag_id: applyTagId, contact_ids: ids } : { tag_id: applyTagId, company_ids: ids };
      await api.post(`/tags/bulk-${mode}`, body);
      toast(`${mode === "apply" ? "Applied" : "Removed"} tag on ${ids.length} ${applyEntity}(s)`, "success");
      setApplyIds("");
      await load();
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Bulk operation failed", "error");
    } finally {
      setApplying(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Tags</h1>
          <p className="mt-0.5 text-sm text-[var(--vbase-slate500)]">
            Reusable labels for segmenting companies and contacts across every view.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setApplyOpen((v) => !v)} className="vbase-btn-secondary flex items-center gap-1.5">
            <IconClipboardList className="h-4 w-4" />
            <span>Bulk apply</span>
          </button>
          <button onClick={openCreate} className="vbase-btn-primary flex items-center gap-1.5">
            <IconPlus className="h-4 w-4" />
            <span>New tag</span>
          </button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Tags" value={tags.length} />
        <StatCard label="Tagged contacts" value={totals.contacts} />
        <StatCard label="Tagged companies" value={totals.companies} />
        <StatCard label="Unused tags" value={totals.unused} tone={totals.unused ? "amber" : undefined} />
      </div>

      {applyOpen && (
        <div className="vbase-card p-5">
          <h3 className="mb-1 font-semibold text-[var(--vbase-slate800)]">Bulk apply or remove a tag</h3>
          <p className="mb-4 text-sm text-[var(--vbase-slate500)]">
            Paste comma-separated record ids. Adding is idempotent — records that already carry the tag are skipped.
          </p>
          <div className="grid gap-3 md:grid-cols-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs uppercase tracking-wider text-[var(--vbase-slate500)]">Tag</span>
              <select
                value={applyTagId}
                onChange={(e) => setApplyTagId(e.target.value ? Number(e.target.value) : "")}
                className="vbase-select"
              >
                <option value="">Select a tag…</option>
                {tags.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs uppercase tracking-wider text-[var(--vbase-slate500)]">Entity</span>
              <select
                value={applyEntity}
                onChange={(e) => setApplyEntity(e.target.value as "contact" | "company")}
                className="vbase-select"
              >
                <option value="contact">Contacts</option>
                <option value="company">Companies</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs uppercase tracking-wider text-[var(--vbase-slate500)]">Record ids</span>
              <input
                value={applyIds}
                onChange={(e) => setApplyIds(e.target.value)}
                placeholder="12, 44, 108"
                className="vbase-input"
              />
            </label>
          </div>
          <div className="mt-4 flex items-center justify-end gap-2">
            <button onClick={() => setApplyOpen(false)} className="vbase-btn-ghost">
              Close
            </button>
            <button
              onClick={() => applyTag("remove")}
              disabled={applying}
              className="vbase-btn-secondary flex items-center gap-1.5"
            >
              {applying ? <IconLoader2 className="h-4 w-4 animate-spin" /> : <IconX className="h-4 w-4" />}
              <span>Remove</span>
            </button>
            <button
              onClick={() => applyTag("apply")}
              disabled={applying}
              className="vbase-btn-primary flex items-center gap-1.5"
            >
              {applying ? <IconLoader2 className="h-4 w-4 animate-spin" /> : <IconCheck className="h-4 w-4" />}
              <span>Apply</span>
            </button>
          </div>
        </div>
      )}

      {(creating || editing) && (
        <div className="vbase-card p-5">
          <h3 className="mb-4 font-semibold text-[var(--vbase-slate800)]">
            {editing ? `Edit “${editing.name}”` : "Create a tag"}
          </h3>
          <div className="grid gap-4 md:grid-cols-3">
            <label className="flex flex-col gap-1 md:col-span-1">
              <span className="text-xs uppercase tracking-wider text-[var(--vbase-slate500)]">Name</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && save()}
                placeholder="e.g. Series B Fintech"
                className="vbase-input"
                autoFocus
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs uppercase tracking-wider text-[var(--vbase-slate500)]">Kind</span>
              <select value={kind} onChange={(e) => setKind(e.target.value)} className="vbase-select">
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex flex-col gap-1">
              <span className="text-xs uppercase tracking-wider text-[var(--vbase-slate500)]">Colour</span>
              <div className="flex items-center gap-2">
                {PALETTE.map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setColor(c)}
                    aria-label={`Colour ${c}`}
                    className={`h-7 w-7 rounded-full border-2 transition-transform ${
                      color === c ? "border-[var(--vbase-slate900)] scale-110" : "border-transparent"
                    }`}
                    style={{ backgroundColor: c }}
                  />
                ))}
              </div>
            </div>
          </div>
          <div className="mt-4 flex items-center justify-end gap-2">
            <button onClick={resetForm} className="vbase-btn-ghost">
              Cancel
            </button>
            <button onClick={save} disabled={saving} className="vbase-btn-primary flex items-center gap-1.5">
              {saving ? <IconLoader2 className="h-4 w-4 animate-spin" /> : <IconCheck className="h-4 w-4" />}
              <span>{editing ? "Save changes" : "Create tag"}</span>
            </button>
          </div>
        </div>
      )}

      <div className="vbase-card overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-[var(--vbase-border)] px-4 py-3">
          <div className="relative flex-1 min-w-[200px]">
            <IconSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--vbase-slate400)]" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter tags…"
              className="vbase-input pl-9"
            />
          </div>
          <select value={kindFilter} onChange={(e) => setKindFilter(e.target.value)} className="vbase-select w-40">
            <option value="">All kinds</option>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
          <span className="text-xs text-[var(--vbase-slate500)]">
            {filtered.length} of {tags.length}
          </span>
        </div>

        {loading ? (
          <div className="flex flex-col items-center gap-2 py-16 text-sm text-[var(--vbase-slate500)]">
            <IconLoader2 className="h-6 w-6 animate-spin text-[var(--vbase-indigo)]" />
            Loading tags…
          </div>
        ) : error ? (
          <div className="flex flex-col items-center gap-2 py-16 text-sm text-[var(--vbase-red)]">
            <IconAlertCircle className="h-6 w-6" />
            {error}
            <button onClick={load} className="vbase-btn-secondary mt-1">
              Retry
            </button>
          </div>
        ) : filtered.length ? (
          <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3">
            {filtered.map((tag) => (
              <div
                key={tag.id}
                className="group flex items-start gap-3 rounded-lg border border-[var(--vbase-border)] bg-[var(--vbase-bg)] p-3 transition-colors hover:border-[var(--vbase-indigo)]/40"
              >
                <span
                  className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md text-xs font-semibold text-white"
                  style={{ backgroundColor: tag.color || "var(--vbase-slate400)" }}
                >
                  {initials(tag.name)}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-[var(--vbase-slate800)]">{tag.name}</p>
                  <p className="mt-0.5 text-xs text-[var(--vbase-slate500)]">
                    {tag.kind || "general"} · {tag.contact_count} contact{tag.contact_count === 1 ? "" : "s"} ·{" "}
                    {tag.company_count} compan{tag.company_count === 1 ? "y" : "ies"}
                  </p>
                </div>
                <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                  <button
                    onClick={() => openEdit(tag)}
                    aria-label={`Edit ${tag.name}`}
                    className="rounded p-1.5 text-[var(--vbase-slate500)] hover:bg-[var(--vbase-bg-alt)] hover:text-[var(--vbase-slate800)]"
                  >
                    <IconEdit className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => setConfirmDelete(tag)}
                    aria-label={`Delete ${tag.name}`}
                    className="rounded p-1.5 text-[var(--vbase-slate500)] hover:bg-[var(--vbase-red)]/10 hover:text-[var(--vbase-red)]"
                  >
                    <IconTrash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 py-16 text-center text-sm text-[var(--vbase-slate500)]">
            <IconTag className="h-8 w-8 text-[var(--vbase-slate300)]" />
            {tags.length ? "No tags match this filter." : "No tags yet — create your first one."}
            {!tags.length && (
              <button onClick={openCreate} className="vbase-btn-primary mt-2 flex items-center gap-1.5">
                <IconPlus className="h-4 w-4" />
                <span>New tag</span>
              </button>
            )}
          </div>
        )}
      </div>

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-xl border border-[var(--vbase-border)] bg-[var(--vbase-bg)] p-6 shadow-xl">
            <h3 className="text-lg font-semibold text-[var(--vbase-slate900)]">Delete “{confirmDelete.name}”?</h3>
            <p className="mt-2 text-sm text-[var(--vbase-slate600)]">
              This removes the tag and its {confirmDelete.contact_count + confirmDelete.company_count} association
              {confirmDelete.contact_count + confirmDelete.company_count === 1 ? "" : "s"}. The records themselves are
              not deleted.
            </p>
            <div className="mt-5 flex items-center justify-end gap-2">
              <button onClick={() => setConfirmDelete(null)} className="vbase-btn-ghost">
                Cancel
              </button>
              <button
                onClick={() => remove(confirmDelete)}
                disabled={deleting}
                className="vbase-btn-danger flex items-center gap-1.5"
              >
                {deleting ? <IconLoader2 className="h-4 w-4 animate-spin" /> : <IconTrash2 className="h-4 w-4" />}
                <span>Delete tag</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, tone }: { label: string; value: number; tone?: "amber" }) {
  return (
    <div className="vbase-card px-4 py-3">
      <p className="text-xs uppercase tracking-wider text-[var(--vbase-slate500)]">{label}</p>
      <p
        className={`mt-1 text-2xl font-semibold ${
          tone === "amber" ? "text-[var(--vbase-amber)]" : "text-[var(--vbase-slate900)]"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
