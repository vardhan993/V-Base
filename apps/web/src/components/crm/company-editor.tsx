import { useState, useCallback, useMemo } from "react";
import { api } from "@/lib/api";
import { Company } from "@/lib/types";
import { toast } from "@/lib/store";
import { IconX } from "@/lib/icons";

/** Editable text form of a company/account. Numeric columns stay strings in
 * the draft so the inputs bind cleanly and are validated on save. */
interface CompanyDraft {
  name: string;
  website: string;
  domain: string;
  linkedin_url: string;
  industry: string;
  sub_industry: string;
  employee_count: string;
  company_size: string;
  country: string;
  state: string;
  city: string;
  headquarters: string;
  founded_year: string;
  technologies: string;
  funding_stage: string;
  company_status: string;
  source: string;
  notes: string;
  tags: string;
  last_verified: string;
}

const EMPTY_DRAFT: CompanyDraft = {
  name: "",
  website: "",
  domain: "",
  linkedin_url: "",
  industry: "",
  sub_industry: "",
  employee_count: "",
  company_size: "",
  country: "",
  state: "",
  city: "",
  headquarters: "",
  founded_year: "",
  technologies: "",
  funding_stage: "",
  company_status: "",
  source: "",
  notes: "",
  tags: "",
  last_verified: "",
};

type StringField = keyof CompanyDraft;

const COMPANY_SIZES = ["", "1-10", "11-50", "51-200", "201-500", "501-1000", "1000+"];

function localDateTime(value: unknown): string {
  if (!value) return "";
  const parsed = value instanceof Date ? value : new Date(String(value));
  if (Number.isNaN(parsed.getTime())) return "";
  const offset = parsed.getTimezoneOffset() * 60000;
  return new Date(parsed.getTime() - offset).toISOString().slice(0, 16);
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function companyToDraft(company: Company | null): CompanyDraft {
  if (!company) return { ...EMPTY_DRAFT };
  return {
    name: company.name ?? "",
    website: company.website ?? "",
    domain: company.domain ?? "",
    linkedin_url: company.linkedin_url ?? "",
    industry: company.industry ?? "",
    sub_industry: company.sub_industry ?? "",
    employee_count: company.employee_count != null ? String(company.employee_count) : "",
    company_size: company.company_size ?? "",
    country: company.country ?? "",
    state: company.state ?? "",
    city: company.city ?? "",
    headquarters: company.headquarters ?? "",
    founded_year: company.founded_year != null ? String(company.founded_year) : "",
    technologies: (company.technologies || []).join(", "),
    funding_stage: company.funding_stage ?? "",
    company_status: company.company_status ?? "",
    source: company.source ?? "",
    notes: company.notes ?? "",
    tags: (company.tag_names || []).join(", "),
    last_verified: localDateTime(company.last_verified),
  };
}

function draftToApi(draft: CompanyDraft): Record<string, unknown> {
  const text = (value: string) => {
    const trimmed = value.trim();
    return trimmed ? trimmed : null;
  };
  const integer = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const parsed = Number.parseInt(trimmed, 10);
    return Number.isNaN(parsed) ? null : parsed;
  };
  return {
    name: draft.name.trim(),
    website: text(draft.website),
    domain: text(draft.domain),
    linkedin_url: text(draft.linkedin_url),
    industry: text(draft.industry),
    sub_industry: text(draft.sub_industry),
    employee_count: integer(draft.employee_count),
    company_size: text(draft.company_size),
    country: text(draft.country),
    state: text(draft.state),
    city: text(draft.city),
    headquarters: text(draft.headquarters),
    founded_year: integer(draft.founded_year),
    technologies: splitList(draft.technologies),
    funding_stage: text(draft.funding_stage),
    company_status: text(draft.company_status),
    source: text(draft.source),
    notes: text(draft.notes),
    last_verified: draft.last_verified ? new Date(draft.last_verified).toISOString() : null,
  };
}

function changedKeys(before: Record<string, unknown>, after: Record<string, unknown>): string[] {
  return Object.keys(after).filter(
    (key) => JSON.stringify(before[key]) !== JSON.stringify(after[key]),
  );
}

export interface CompanyEditorProps {
  /** Pass a company to edit it; omit or pass null to create a new one. */
  company?: Company | null;
  onSaved: (company: Company) => void;
  onDelete?: (company: Company) => void;
  onCancel?: () => void;
}

interface FieldRowProps {
  label: string;
  value: string;
  onClear: () => void;
  note?: string;
  children: React.ReactNode;
}

function FieldRow({ label, value, onClear, note, children }: FieldRowProps) {
  const clearable = value.trim().length > 0;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <label className="text-xs font-medium text-[var(--vbase-slate500)]">{label}</label>
        {clearable && (
          <button
            type="button"
            onClick={onClear}
            title={`Clear ${label}`}
            aria-label={`Clear ${label}`}
            className="vbase-btn vbase-btn-icon-sm vbase-btn-ghost text-[var(--vbase-slate400)]"
          >
            <IconX className="h-3 w-3" />
          </button>
        )}
      </div>
      <div className="mt-0.5">{children}</div>
      {note && <p className="mt-0.5 text-[11px] text-[var(--vbase-slate500)]">{note}</p>}
    </div>
  );
}

export function CompanyEditor({ company, onSaved, onDelete, onCancel }: CompanyEditorProps) {
  const isCreate = !company;
  const original = useMemo(() => companyToDraft(company ?? null), [company]);
  const [draft, setDraft] = useState<CompanyDraft>(() => companyToDraft(company ?? null));
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [archived, setArchived] = useState(company?.is_archived ?? false);
  const [invalid, setInvalid] = useState<string | null>(null);

  const setValue = useCallback((field: StringField, value: string) => {
    setDraft((prev) => ({ ...prev, [field]: value }));
  }, []);

  const nextBody = useMemo(() => draftToApi(draft), [draft]);
  const baseline = useMemo(() => draftToApi(original), [original]);
  const changed = useMemo(() => changedKeys(baseline, nextBody), [baseline, nextBody]);
  const changedTags = useMemo(
    () => JSON.stringify(splitList(draft.tags)) !== JSON.stringify(splitList(original.tags)),
    [draft.tags, original.tags],
  );

  const busy = saving || deleting;

  const save = async () => {
    setInvalid(null);
    if (!draft.name.trim()) {
      setInvalid("A company name is required.");
      return;
    }
    if (!isCreate && !changed.length && !changedTags) {
      toast("No changes", "info");
      return;
    }

    setSaving(true);
    try {
      let saved: Company;
      if (isCreate) {
        saved = await api.post<Company>("/companies", nextBody);
        if (draft.tags.trim()) {
          saved = await api.patch<Company>(`/companies/${saved.id}`, { tags: splitList(draft.tags) });
        }
        toast("Company created", "success");
      } else {
        const body: Record<string, unknown> = {};
        for (const key of changed) body[key] = nextBody[key];
        if (changedTags) body.tags = splitList(draft.tags);
        saved = await api.patch<Company>(`/companies/${company!.id}`, body);
        toast("Company updated", "success");
      }
      setDraft(companyToDraft(saved));
      setArchived(saved.is_archived);
      onSaved(saved);
    } catch (e: any) {
      const detail = e?.data?.detail;
      const message = Array.isArray(detail)
        ? detail.map((d: any) => d?.msg || JSON.stringify(d)).join("; ")
        : detail || e?.message || "Save failed";
      setInvalid(message);
      toast(message, "error");
    } finally {
      setSaving(false);
    }
  };

  const discard = () => {
    setDraft(companyToDraft(company ?? null));
    setInvalid(null);
  };

  const setArchivedFlag = async (next: boolean) => {
    if (!company) return;
    setSaving(true);
    try {
      const updated = await api.post<Company>(
        `/companies/${company.id}/${next ? "archive" : "restore"}`,
      );
      setArchived(updated.is_archived);
      setDraft(companyToDraft(updated));
      onSaved(updated);
      toast(next ? "Company archived" : "Company restored", "success");
    } catch (e: any) {
      toast(e?.data?.detail || "Could not update archive state", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!company) return;
    if (
      !window.confirm(
        `Delete ${company.name}? Linked contacts are kept but detached. This cannot be undone.`,
      )
    ) {
      return;
    }
    setDeleting(true);
    try {
      await api.delete(`/companies/${company.id}`);
      toast("Company deleted", "success");
      onDelete?.(company);
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Delete failed", "error");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      {invalid && (
        <div
          role="alert"
          className="rounded-md border border-[var(--vbase-red)]/30 bg-[var(--vbase-red)]/5 p-3 text-sm text-[var(--vbase-red)]"
        >
          {invalid}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-[var(--vbase-slate500)]">
          {isCreate
            ? "Only the company name is required — add the rest as you learn it."
            : "Edit any single field and save. Use the × beside a label to clear just that field."}
        </p>
        {!isCreate && (changed.length > 0 || changedTags) && (
          <span className="text-xs text-[var(--vbase-indigo)]">
            {changed.length + (changedTags ? 1 : 0)} field(s) changed
          </span>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <FieldRow label="Company name" value={draft.name} onClear={() => setValue("name", "")} note="Required.">
          <input
            type="text"
            name="name"
            value={draft.name}
            onChange={(e) => setValue("name", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
            autoComplete="off"
            required
          />
        </FieldRow>
        <FieldRow label="Website" value={draft.website} onClear={() => setValue("website", "")}>
          <input
            type="url"
            name="website"
            value={draft.website}
            onChange={(e) => setValue("website", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
            autoComplete="off"
          />
        </FieldRow>
        <FieldRow label="Domain" value={draft.domain} onClear={() => setValue("domain", "")} note="e.g. acme.com">
          <input
            type="text"
            name="domain"
            value={draft.domain}
            onChange={(e) => setValue("domain", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
            autoComplete="off"
          />
        </FieldRow>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <FieldRow label="Industry" value={draft.industry} onClear={() => setValue("industry", "")}>
          <input
            type="text"
            name="industry"
            value={draft.industry}
            onChange={(e) => setValue("industry", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
        <FieldRow label="Sub-industry" value={draft.sub_industry} onClear={() => setValue("sub_industry", "")}>
          <input
            type="text"
            name="sub_industry"
            value={draft.sub_industry}
            onChange={(e) => setValue("sub_industry", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
        <FieldRow
          label="Employees"
          value={draft.employee_count}
          onClear={() => setValue("employee_count", "")}
          note="Whole number."
        >
          <input
            type="number"
            min={0}
            name="employee_count"
            value={draft.employee_count}
            onChange={(e) => setValue("employee_count", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <FieldRow label="Size band" value={draft.company_size} onClear={() => setValue("company_size", "")}>
          <select
            name="company_size"
            value={draft.company_size}
            onChange={(e) => setValue("company_size", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          >
            {COMPANY_SIZES.map((size) => (
              <option key={size || "unset"} value={size}>
                {size || "Size band"}
              </option>
            ))}
          </select>
        </FieldRow>
        <FieldRow
          label="Founded"
          value={draft.founded_year}
          onClear={() => setValue("founded_year", "")}
          note="Four-digit year."
        >
          <input
            type="number"
            min={1500}
            max={2100}
            name="founded_year"
            value={draft.founded_year}
            onChange={(e) => setValue("founded_year", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
        <FieldRow label="LinkedIn" value={draft.linkedin_url} onClear={() => setValue("linkedin_url", "")}>
          <input
            type="url"
            name="linkedin_url"
            value={draft.linkedin_url}
            onChange={(e) => setValue("linkedin_url", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
            autoComplete="off"
          />
        </FieldRow>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <FieldRow label="Headquarters" value={draft.headquarters} onClear={() => setValue("headquarters", "")}>
          <input
            type="text"
            name="headquarters"
            value={draft.headquarters}
            onChange={(e) => setValue("headquarters", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
        <FieldRow label="City" value={draft.city} onClear={() => setValue("city", "")}>
          <input
            type="text"
            name="city"
            value={draft.city}
            onChange={(e) => setValue("city", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
        <FieldRow label="State" value={draft.state} onClear={() => setValue("state", "")}>
          <input
            type="text"
            name="state"
            value={draft.state}
            onChange={(e) => setValue("state", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
        <FieldRow label="Country" value={draft.country} onClear={() => setValue("country", "")}>
          <input
            type="text"
            name="country"
            value={draft.country}
            onChange={(e) => setValue("country", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <FieldRow label="Funding stage" value={draft.funding_stage} onClear={() => setValue("funding_stage", "")}>
          <input
            type="text"
            name="funding_stage"
            value={draft.funding_stage}
            onChange={(e) => setValue("funding_stage", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
        <FieldRow label="Account status" value={draft.company_status} onClear={() => setValue("company_status", "")}>
          <input
            type="text"
            name="company_status"
            value={draft.company_status}
            onChange={(e) => setValue("company_status", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
        <FieldRow label="Source" value={draft.source} onClear={() => setValue("source", "")}>
          <input
            type="text"
            name="source"
            value={draft.source}
            onChange={(e) => setValue("source", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <FieldRow label="Technologies" value={draft.technologies} onClear={() => setValue("technologies", "")} note="Comma separated.">
          <input
            type="text"
            name="technologies"
            value={draft.technologies}
            onChange={(e) => setValue("technologies", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
        <FieldRow label="Tags" value={draft.tags} onClear={() => setValue("tags", "")} note="Comma separated.">
          <input
            type="text"
            name="tags"
            value={draft.tags}
            onChange={(e) => setValue("tags", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
        <FieldRow label="Last verified" value={draft.last_verified} onClear={() => setValue("last_verified", "")}>
          <input
            type="datetime-local"
            name="last_verified"
            value={draft.last_verified}
            onChange={(e) => setValue("last_verified", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
      </div>

      <FieldRow label="Notes" value={draft.notes} onClear={() => setValue("notes", "")}>
        <textarea
          rows={4}
          name="notes"
          value={draft.notes}
          onChange={(e) => setValue("notes", e.target.value)}
          className="vbase-input w-full resize-y"
          disabled={busy}
        />
      </FieldRow>

      <div className="flex flex-wrap items-center gap-3 border-t border-[var(--vbase-border)] pt-4">
        <button onClick={save} className="vbase-btn-primary" disabled={busy}>
          {saving ? "Saving…" : isCreate ? "Create company" : "Save changes"}
        </button>
        {!isCreate && (
          <button onClick={discard} className="vbase-btn-ghost text-sm" disabled={busy}>
            Discard
          </button>
        )}
        {onCancel && (
          <button onClick={onCancel} className="vbase-btn-ghost text-sm" disabled={busy}>
            Cancel
          </button>
        )}
        <span className="text-xs text-[var(--vbase-slate500)]">
          {isCreate
            ? "Contacts can be linked to this company from the contact editor."
            : changed.length || changedTags
              ? "Only the fields you changed are sent."
              : "No changes yet."}
        </span>
      </div>

      {!isCreate && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--vbase-border)] pt-4">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setArchivedFlag(!archived)}
              disabled={busy}
              className={
                archived
                  ? "vbase-btn-secondary flex items-center gap-1.5 text-sm"
                  : "vbase-btn-ghost flex items-center gap-1.5 text-sm text-[var(--vbase-amber)]"
              }
            >
              {archived ? "Restore" : "Archive"}
            </button>
            <span className="text-xs text-[var(--vbase-slate500)]">{archived ? "Archived" : "Active"}</span>
          </div>
          <button
            onClick={handleDelete}
            disabled={busy}
            className="vbase-btn-danger flex items-center gap-1.5 text-sm"
          >
            Delete company
          </button>
        </div>
      )}
    </div>
  );
}
