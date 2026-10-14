import { useState, useCallback, useMemo } from "react";
import { api } from "@/lib/api";
import { Contact } from "@/lib/types";
import { CRM_STAGES } from "@/lib/crm";
import { toast } from "@/lib/store";
import { IconX } from "@/lib/icons";

/** Editable text form of a contact. Everything is a string (or newline /
 * comma separated list) so a single input binding covers every column, and
 * empty strings normalize to null / [] on the way to the API. */
interface ContactDraft {
  first_name: string;
  last_name: string;
  full_name: string;
  job_title: string;
  department: string;
  seniority: string;
  email: string;
  email_status: string;
  phone: string;
  phone_status: string;
  stage: string;
  linkedin_url: string;
  company_name: string;
  city: string;
  country: string;
  source: string;
  notes: string;
  skills: string;
  employment_history: string;
  last_verified: string;
  tags: string;
}

const EMPTY_DRAFT: ContactDraft = {
  first_name: "",
  last_name: "",
  full_name: "",
  job_title: "",
  department: "",
  seniority: "",
  email: "",
  email_status: "",
  phone: "",
  phone_status: "",
  stage: "New",
  linkedin_url: "",
  company_name: "",
  city: "",
  country: "",
  source: "",
  notes: "",
  skills: "",
  employment_history: "",
  last_verified: "",
  tags: "",
};

type StringField = Exclude<keyof ContactDraft, never>;

const EMAIL_STATUS_OPTIONS = ["", "Verified", "Pending", "Invalid", "Missing"];
const PHONE_STATUS_OPTIONS = ["", "Verified", "Pending", "Invalid", "Missing"];

function localDateTime(value: unknown): string {
  if (!value) return "";
  const parsed = value instanceof Date ? value : new Date(String(value));
  if (Number.isNaN(parsed.getTime())) return "";
  // datetime-local wants local wall-clock time, not the UTC ISO form.
  const offset = parsed.getTimezoneOffset() * 60000;
  return new Date(parsed.getTime() - offset).toISOString().slice(0, 16);
}

function splitSkills(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function parseHistory(value: string): Record<string, string>[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [company_name = "", job_title = "", start_date = "", end_date = ""] = line
        .split(",")
        .map((part) => part.trim());
      const entry: Record<string, string> = {};
      if (company_name) entry.company_name = company_name;
      if (job_title) entry.job_title = job_title;
      if (start_date) entry.start_date = start_date;
      if (end_date) entry.end_date = end_date;
      return entry;
    });
}

function historyToText(entries: unknown): string {
  if (!Array.isArray(entries)) return "";
  return entries
    .map((raw) => {
      const e = (raw || {}) as Record<string, unknown>;
      return [e.company_name, e.job_title, e.start_date, e.end_date]
        .filter((part) => part !== null && part !== undefined && part !== "")
        .join(", ");
    })
    .join("\n");
}

function contactToDraft(contact: Contact | null): ContactDraft {
  if (!contact) return { ...EMPTY_DRAFT };
  return {
    first_name: contact.first_name ?? "",
    last_name: contact.last_name ?? "",
    full_name: contact.full_name ?? "",
    job_title: contact.job_title ?? "",
    department: contact.department ?? "",
    seniority: contact.seniority ?? "",
    email: contact.email ?? "",
    email_status: contact.email_status ?? "",
    phone: contact.phone ?? "",
    phone_status: contact.phone_status ?? "",
    stage: contact.stage || "New",
    linkedin_url: contact.linkedin_url ?? "",
    company_name: contact.company_name ?? "",
    city: contact.city ?? "",
    country: contact.country ?? "",
    source: contact.source ?? "",
    notes: contact.notes ?? "",
    skills: (contact.skills || []).join(", "),
    employment_history: historyToText(contact.employment_history),
    last_verified: localDateTime(contact.last_verified),
    tags: (contact.tag_names || []).join(", "),
  };
}

/** API body for the writable columns. Stage and the list columns are never
 * null because the backend response model requires a string / list there. */
function draftToApi(draft: ContactDraft): Record<string, unknown> {
  const text = (value: string) => {
    const trimmed = value.trim();
    return trimmed ? trimmed : null;
  };
  return {
    first_name: text(draft.first_name),
    last_name: text(draft.last_name),
    full_name: text(draft.full_name),
    job_title: text(draft.job_title),
    department: text(draft.department),
    seniority: text(draft.seniority),
    email: text(draft.email),
    email_status: text(draft.email_status),
    phone: text(draft.phone),
    phone_status: text(draft.phone_status),
    stage: draft.stage || "New",
    linkedin_url: text(draft.linkedin_url),
    company_name: text(draft.company_name),
    city: text(draft.city),
    country: text(draft.country),
    source: text(draft.source),
    notes: text(draft.notes),
    skills: splitSkills(draft.skills),
    employment_history: parseHistory(draft.employment_history),
    last_verified: draft.last_verified ? new Date(draft.last_verified).toISOString() : null,
  };
}

/** Keys whose value actually differs between two API bodies. */
function changedKeys(before: Record<string, unknown>, after: Record<string, unknown>): string[] {
  return Object.keys(after).filter(
    (key) => JSON.stringify(before[key]) !== JSON.stringify(after[key]),
  );
}

export interface ContactEditorProps {
  /** Pass a contact to edit it; omit or pass null to create a new one. */
  contact?: Contact | null;
  company?: { id: number; name: string } | null;
  onSaved: (contact: Contact) => void;
  onDelete?: (contact: Contact) => void;
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

export function ContactEditor({ contact, company, onSaved, onDelete, onCancel }: ContactEditorProps) {
  const isCreate = !contact;
  const original = useMemo(() => contactToDraft(contact ?? null), [contact]);
  const [draft, setDraft] = useState<ContactDraft>(() => contactToDraft(contact ?? null));
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [archived, setArchived] = useState(contact?.is_archived ?? false);
  const [invalid, setInvalid] = useState<string | null>(null);

  const setValue = useCallback((field: StringField, value: string) => {
    setDraft((prev) => ({ ...prev, [field]: value }));
  }, []);

  const nextBody = useMemo(() => draftToApi(draft), [draft]);
  const baseline = useMemo(() => draftToApi(original), [original]);
  const changed = useMemo(() => changedKeys(baseline, nextBody), [baseline, nextBody]);
  const changedTags = useMemo(
    () => JSON.stringify(splitSkills(draft.tags)) !== JSON.stringify(splitSkills(original.tags)),
    [draft.tags, original.tags],
  );

  const busy = saving || deleting;

  const save = async () => {
    setInvalid(null);
    if (isCreate) {
      const hasIdentity =
        draft.first_name.trim() ||
        draft.last_name.trim() ||
        draft.full_name.trim() ||
        draft.email.trim();
      if (!hasIdentity) {
        setInvalid("Add at least a name or an email address before saving.");
        return;
      }
    } else if (!changed.length && !changedTags) {
      toast("No changes", "info");
      return;
    }

    setSaving(true);
    try {
      let saved: Contact;
      if (isCreate) {
        saved = await api.post<Contact>("/contacts", nextBody);
        if (draft.tags.trim()) {
          saved = await api.patch<Contact>(`/contacts/${saved.id}`, { tags: splitSkills(draft.tags) });
        }
        toast("Contact created", "success");
      } else {
        const body: Record<string, unknown> = {};
        for (const key of changed) body[key] = nextBody[key];
        if (changedTags) body.tags = splitSkills(draft.tags);
        saved = await api.patch<Contact>(`/contacts/${contact!.id}`, body);
        toast("Contact updated", "success");
      }
      setDraft(contactToDraft(saved));
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
    setDraft(contactToDraft(contact ?? null));
    setInvalid(null);
  };

  const setArchivedFlag = async (next: boolean) => {
    if (!contact) return;
    setSaving(true);
    try {
      const updated = await api.post<Contact>(
        `/contacts/${contact.id}/${next ? "archive" : "restore"}`,
      );
      setArchived(updated.is_archived);
      setDraft(contactToDraft(updated));
      onSaved(updated);
      toast(next ? "Contact archived" : "Contact restored", "success");
    } catch (e: any) {
      toast(e?.data?.detail || "Could not update archive state", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!contact) return;
    if (!window.confirm("Delete this contact? This cannot be undone.")) return;
    setDeleting(true);
    try {
      await api.delete(`/contacts/${contact.id}`);
      toast("Contact deleted", "success");
      onDelete?.(contact);
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
            ? "Fill in what you know — everything except a name or email can be added later."
            : "Edit any single field and save. Use the × beside a label to clear just that field."}
        </p>
        {!isCreate && (changed.length > 0 || changedTags) && (
          <span className="text-xs text-[var(--vbase-indigo)]">
            {changed.length + (changedTags ? 1 : 0)} field(s) changed
          </span>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <FieldRow label="First name" value={draft.first_name} onClear={() => setValue("first_name", "")}>
          <input
            type="text"
            name="first_name"
            value={draft.first_name}
            onChange={(e) => setValue("first_name", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
            autoComplete="off"
          />
        </FieldRow>
        <FieldRow label="Last name" value={draft.last_name} onClear={() => setValue("last_name", "")}>
          <input
            type="text"
            name="last_name"
            value={draft.last_name}
            onChange={(e) => setValue("last_name", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
            autoComplete="off"
          />
        </FieldRow>
        <FieldRow
          label="Full name"
          value={draft.full_name}
          onClear={() => setValue("full_name", "")}
          note="Auto-derived from first/last when left blank."
        >
          <input
            type="text"
            name="full_name"
            value={draft.full_name}
            onChange={(e) => setValue("full_name", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
            autoComplete="off"
          />
        </FieldRow>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <FieldRow label="Job title" value={draft.job_title} onClear={() => setValue("job_title", "")}>
          <input
            type="text"
            name="job_title"
            value={draft.job_title}
            onChange={(e) => setValue("job_title", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
        <FieldRow label="Department" value={draft.department} onClear={() => setValue("department", "")}>
          <input
            type="text"
            name="department"
            value={draft.department}
            onChange={(e) => setValue("department", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
        <FieldRow label="Seniority" value={draft.seniority} onClear={() => setValue("seniority", "")}>
          <input
            type="text"
            name="seniority"
            value={draft.seniority}
            onChange={(e) => setValue("seniority", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <FieldRow label="Email" value={draft.email} onClear={() => setValue("email", "")}>
          <input
            type="email"
            name="email"
            value={draft.email}
            onChange={(e) => setValue("email", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
            autoComplete="off"
          />
        </FieldRow>
        <FieldRow label="Email status" value={draft.email_status} onClear={() => setValue("email_status", "")}>
          <select
            name="email_status"
            value={draft.email_status}
            onChange={(e) => setValue("email_status", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          >
            {EMAIL_STATUS_OPTIONS.map((value) => (
              <option key={value || "unset"} value={value}>
                {value || "Email status"}
              </option>
            ))}
          </select>
        </FieldRow>
        <FieldRow
          label="Phone"
          value={draft.phone}
          onClear={() => setValue("phone", "")}
          note="Include the country code (+91, +1) so it dials from anywhere."
        >
          <input
            type="tel"
            name="phone"
            value={draft.phone}
            onChange={(e) => setValue("phone", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
            autoComplete="off"
          />
        </FieldRow>
        <FieldRow label="Phone status" value={draft.phone_status} onClear={() => setValue("phone_status", "")}>
          <select
            name="phone_status"
            value={draft.phone_status}
            onChange={(e) => setValue("phone_status", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          >
            {PHONE_STATUS_OPTIONS.map((value) => (
              <option key={value || "unset"} value={value}>
                {value || "Phone status"}
              </option>
            ))}
          </select>
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
        <FieldRow
          label="Stage"
          value={draft.stage}
          onClear={() => setValue("stage", "New")}
        >
          <select
            name="stage"
            value={draft.stage}
            onChange={(e) => setValue("stage", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          >
            {CRM_STAGES.map((stage) => (
              <option key={stage} value={stage}>
                {stage}
              </option>
            ))}
          </select>
        </FieldRow>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <FieldRow
          label="Company"
          value={draft.company_name}
          onClear={() => setValue("company_name", "")}
          note="Matching an existing company links the record; clearing unlinks it."
        >
          <input
            type="text"
            name="company_name"
            value={draft.company_name}
            onChange={(e) => setValue("company_name", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
            autoComplete="off"
            list="vbase-company-names"
          />
          <datalist id="vbase-company-names">
            {company ? <option value={company.name} /> : null}
          </datalist>
        </FieldRow>
        <FieldRow label="Linked company" value={company?.name ?? ""} onClear={() => undefined}>
          <span className="text-sm text-[var(--vbase-slate700)]">
            {company ? (
              <>
                <span className="font-medium">{company.name}</span>
                <span className="ml-1 text-[var(--vbase-slate500)]">(id {company.id})</span>
              </>
            ) : (
              <span className="text-[var(--vbase-slate400)]">Not linked</span>
            )}
          </span>
        </FieldRow>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
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

      <div className="grid gap-4 md:grid-cols-2">
        <FieldRow label="Skills" value={draft.skills} onClear={() => setValue("skills", "")} note="Comma separated.">
          <input
            type="text"
            name="skills"
            value={draft.skills}
            onChange={(e) => setValue("skills", e.target.value)}
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
        <FieldRow
          label="Last verified"
          value={draft.last_verified}
          onClear={() => setValue("last_verified", "")}
          note="When this record's details were last confirmed."
        >
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

      <FieldRow
        label="Employment history"
        value={draft.employment_history}
        onClear={() => setValue("employment_history", "")}
        note="One per line: Company, Job title, Start, End."
      >
        <textarea
          rows={3}
          name="employment_history"
          value={draft.employment_history}
          onChange={(e) => setValue("employment_history", e.target.value)}
          className="vbase-input w-full resize-y"
          disabled={busy}
        />
      </FieldRow>

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
          {saving ? "Saving…" : isCreate ? "Create contact" : "Save changes"}
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
            ? "Saved contacts appear in search, pipeline and export immediately."
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
            Delete contact
          </button>
        </div>
      )}
    </div>
  );
}
