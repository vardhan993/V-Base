import { useState, useEffect, useCallback } from "react";
import { IconPlus, IconTrash2, IconTag } from "@/lib/icons";
import { api } from "@/lib/api";
import { toast } from "@/lib/store";

interface CustomField {
  id: number;
  entity_type: string;
  name: string;
  key: string;
  field_type: string;
  is_required: boolean;
  options?: string[] | null;
}

const FIELD_TYPES = ["text", "long_text", "number", "date", "url", "email", "phone", "boolean", "single_select", "multi_select"];

export function CustomFieldsPage() {
  const [fields, setFields] = useState<CustomField[]>([]);
  const [, setLoading] = useState(false);
  const [entity, setEntity] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [newEntity, setNewEntity] = useState("contact");
  const [fieldType, setFieldType] = useState("text");
  const [options, setOptions] = useState("");

  const fetchFields = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<CustomField[]>("/custom-fields", { params: entity ? { entity_type: entity } : {} });
      setFields(data);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, [entity]);

  useEffect(() => { fetchFields(); }, [fetchFields]);

  const create = async () => {
    if (!name.trim()) { toast("Name is required", "error"); return; }
    const needsOptions = fieldType === "single_select" || fieldType === "multi_select";
    const opts = needsOptions ? options.split(",").map((s) => s.trim()).filter(Boolean) : undefined;
    if (needsOptions && !opts?.length) { toast("Select fields need comma-separated options", "error"); return; }
    try {
      await api.post("/custom-fields", { name: name.trim(), entity_type: newEntity, field_type: fieldType, options: opts });
      toast("Custom field created", "success");
      setName(""); setOptions(""); setCreateOpen(false);
      fetchFields();
    } catch (e: any) { toast(e?.data?.detail || e?.message || "Create failed", "error"); }
  };

  const remove = async (id: number) => {
    if (!window.confirm("Delete this field and all its values? This cannot be undone.")) return;
    try {
      await api.delete(`/custom-fields/${id}`);
      toast("Custom field deleted", "success");
      fetchFields();
    } catch (e: any) { toast(e?.data?.detail || e?.message || "Delete failed", "error"); }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Custom Fields</h1>
        <div className="flex items-center gap-2">
          <select value={entity} onChange={(e) => setEntity(e.target.value)} className="vbase-select max-w-[160px]">
            <option value="">All entities</option>
            <option value="contact">Contacts</option>
            <option value="company">Companies</option>
          </select>
          <button onClick={() => setCreateOpen(true)} className="vbase-btn-primary flex items-center gap-1.5"><IconPlus className="h-4 w-4" /><span>New field</span></button>
        </div>
      </div>

      {createOpen && (
        <div className="vbase-card p-6">
          <h3 className="mb-4 font-semibold text-[var(--vbase-slate800)]">Create custom field</h3>
          <div className="space-y-4">
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Field name (e.g. Funding Round)" className="vbase-input" />
            <div className="grid gap-4 md:grid-cols-2">
              <select value={newEntity} onChange={(e) => setNewEntity(e.target.value)} className="vbase-select">
                <option value="contact">Contact</option>
                <option value="company">Company</option>
              </select>
              <select value={fieldType} onChange={(e) => setFieldType(e.target.value)} className="vbase-select">
                {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            {(fieldType === "single_select" || fieldType === "multi_select") && (
              <input type="text" value={options} onChange={(e) => setOptions(e.target.value)} placeholder="Options, comma-separated" className="vbase-input" />
            )}
            <div className="flex items-center justify-end gap-2">
              <button onClick={() => setCreateOpen(false)} className="vbase-btn-ghost">Cancel</button>
              <button onClick={create} className="vbase-btn-primary">Save</button>
            </div>
          </div>
        </div>
      )}

      <div className="vbase-card overflow-hidden">
        <div className="border-b border-[var(--vbase-border)] px-4 py-3">
          <h3 className="font-semibold text-[var(--vbase-slate800)]">Extra fields for contacts and companies</h3>
        </div>
        {fields.map((f) => (
          <div key={f.id} className="flex items-center gap-3 px-4 py-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-[var(--vbase-bg-alt)]">
              <IconTag className="h-4 w-4 text-[var(--vbase-slate500)]" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-medium text-[var(--vbase-slate800)]">{f.name}</p>
              <p className="text-xs text-[var(--vbase-slate500)]">{f.entity_type} · {f.field_type}{f.options?.length ? ` · ${f.options.join(", ")}` : ""}</p>
            </div>
            <code className="text-xs text-[var(--vbase-slate400)]">{f.key}</code>
            <button onClick={() => remove(f.id)} className="vbase-btn-danger flex items-center gap-1"><IconTrash2 className="h-4 w-4" /><span>Delete</span></button>
          </div>
        ))}
        {!fields.length && (
          <div className="px-4 py-12 text-center text-sm text-[var(--vbase-slate500)]">
            <IconTag className="h-8 w-8 mx-auto mb-2 text-[var(--vbase-slate300)]" />
            No custom fields yet
          </div>
        )}
      </div>
    </div>
  );
}
