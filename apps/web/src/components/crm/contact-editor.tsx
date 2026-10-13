import { useState, useCallback } from "react";
import { api } from "@/lib/api";
import { Contact } from "@/lib/types";
import { CRM_STAGES } from "@/lib/crm";
import { toast } from "@/lib/store";

export interface ContactEditorProps {
  contact: Contact;
  company?: { id: number; name: string } | null;
  onSaved: (contact: Contact) => void;
  onDelete?: (contact: Contact) => void;
}

type EditField =
  | "first_name"
  | "last_name"
  | "full_name"
  | "job_title"
  | "department"
  | "seniority"
  | "email"
  | "email_status"
  | "phone"
  | "phone_status"
  | "linkedin_url"
  | "company_name"
  | "city"
  | "country"
  | "source"
  | "notes"
  | "stage"
  | "skills"
  | "employment_history"
  | "last_verified";

const EMAIL_STATUS_OPTIONS = [
  { value: "", label: "Email status" },
  { value: "Verified", label: "Verified" },
  { value: "Pending", label: "Pending" },
  { value: "Invalid", label: "Invalid" },
  { value: "Missing", label: "Missing" },
];

const PHONE_STATUS_OPTIONS = [
  { value: "", label: "Phone status" },
  { value: "Verified", label: "Verified" },
  { value: "Pending", label: "Pending" },
  { value: "Invalid", label: "Invalid" },
  { value: "Missing", label: "Missing" },
];

const STAGE_OPTIONS = CRM_STAGES.map((s) => ({ value: s, label: s }));

interface FieldRowProps {
  label: string;
  children: React.ReactNode;
  note?: string;
}

function FieldRow({ label, children, note }: FieldRowProps) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-[var(--vbase-slate500)]">{label}</label>
      <div className="mt-0.5">{children}</div>
      {note && <p className="mt-0.5 text-[11px] text-[var(--vbase-slate500)]">{note}</p>}
    </div>
  );
}

export function ContactEditor({ contact, company, onSaved, onDelete }: ContactEditorProps) {
  const start = contact;
  const [draft, setDraft] = useState<Contact>(contact);  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [archived, setArchived] = useState(contact.is_archived);
  const [invalid, setInvalid] = useState<string | null>(null);

  const stageDraft: string = draft.stage;

  const setValue = useCallback(
    (field: EditField, value: string | boolean | number | string[] | Record<string, unknown>[] | null | undefined) => {
      setDraft((prev) => {
        const next = { ...prev };
        if (field === "stage") {
          if (value === null || value === undefined || value === "") {
            (next as any)[field] = "New";
          } else if (typeof value === "string" && CRM_STAGES.includes(value)) {
            (next as any)[field] = value;
          }
        } else {
          (next as any)[field] = value;
        }
        return next;
      });
    },
    []
  );

  const fillFromDraft = useCallback(() => {
    setDraft({ ...contact });
    setInvalid(null);
  }, [contact]);

  const computeChanges = () => {
    const fields: string[] = [];
    if (contact.first_name !== draft.first_name) fields.push("first_name");
    if (contact.last_name !== draft.last_name) fields.push("last_name");
    if (contact.full_name !== draft.full_name) fields.push("full_name");
    if (contact.job_title !== draft.job_title) fields.push("job_title");
    if (contact.department !== draft.department) fields.push("department");
    if (contact.seniority !== draft.seniority) fields.push("seniority");
    if (contact.email !== draft.email) fields.push("email");
    if (contact.email_status !== draft.email_status) fields.push("email_status");
    if (contact.phone !== draft.phone) fields.push("phone");
    if (contact.phone_status !== draft.phone_status) fields.push("phone_status");
    if (contact.linkedin_url !== draft.linkedin_url) fields.push("linkedin_url");
    if (contact.company_name !== draft.company_name) fields.push("company_name");
    if (contact.city !== draft.city) fields.push("city");
    if (contact.country !== draft.country) fields.push("country");
    if (contact.source !== draft.source) fields.push("source");
    if (contact.notes !== draft.notes) fields.push("notes");
    if (JSON.stringify(contact.skills) !== JSON.stringify(draft.skills)) fields.push("skills");
    if (JSON.stringify(contact.employment_history) !== JSON.stringify(draft.employment_history)) fields.push("employment_history");
    if (contact.stage !== draft.stage) fields.push("stage");
    if (contact.last_verified !== draft.last_verified) fields.push("last_verified");
    return fields;
  };

  const hasChanges = computeChanges().length > 0;

  const save = async () => {
    setSaving(true);
    try {
      const changes = computeChanges();
      if (!changes.length) {
        toast("No changes", "info");
        return;
      }

      const body: any = {};
      if (draft.first_name !== undefined) body.first_name = draft.first_name;
      if (draft.last_name !== undefined) body.last_name = draft.last_name;
      if (draft.full_name !== undefined) body.full_name = draft.full_name;
      if (draft.job_title !== undefined) body.job_title = draft.job_title;
      if (draft.department !== undefined) body.department = draft.department;
      if (draft.seniority !== undefined) body.seniority = draft.seniority;
      if (draft.email !== undefined) body.email = draft.email;
      if (draft.email_status !== undefined) body.email_status = draft.email_status;
      if (draft.phone !== undefined) body.phone = draft.phone;
      if (draft.phone_status !== undefined) body.phone_status = draft.phone_status;
      if (draft.linkedin_url !== undefined) body.linkedin_url = draft.linkedin_url;
      if (draft.company_name !== undefined) body.company_name = draft.company_name;
      if (draft.city !== undefined) body.city = draft.city;
      if (draft.country !== undefined) body.country = draft.country;
      if (draft.source !== undefined) body.source = draft.source;
      if (draft.notes !== undefined) body.notes = draft.notes;
      if (draft.skills.length === 0 || draft.skills.join(",") === "") body.skills = [];
      if (draft.skills.length) body.skills = draft.skills;
      if (draft.employment_history.length === 0 || !draft.employment_history) body.employment_history = [];
      if (draft.employment_history.length) body.employment_history = draft.employment_history;
      if (draft.stage !== undefined) body.stage = draft.stage;
      if (draft.last_verified !== undefined) body.last_verified = draft.last_verified;

      let updated: Contact;
      try {
        updated = await api.patch<Contact>(`/contacts/${contact.id}`, body);
      } catch (err: any) {
        // Some backends return a 422 with a list; treat it as a typed validation
        // error and let the user fix it rather than swallowing the message.
        setInvalid(err?.data?.detail || err?.message || "Validation failed");
        throw err;
      }
      onSaved(updated);
      toast("Contact updated", "success");
      setDraft({ ...updated });
      setInvalid(null);
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Save failed", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleArchive = async () => {
    setSaving(true);
    try {
      const updated = await api.post<Contact>(`/contacts/${contact.id}/archive`);
      setArchived(true);
      onSaved(updated);
      toast("Contact archived", "success");
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Archive failed", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleRestore = async () => {
    setSaving(true);
    try {
      const updated = await api.post<Contact>(`/contacts/${contact.id}/restore`);
      setArchived(false);
      onSaved(updated);
      toast("Contact restored", "success");
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Restore failed", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(`Delete this contact? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await api.delete(`/contacts/${contact.id}`);
      if (onDelete) onDelete(contact);
      toast("Contact deleted", "success");
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Delete failed", "error");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      {invalid && (
        <div className="rounded-md border border-[var(--vbase-red)]/30 bg-[var(--vbase-red)]/5 p-3 text-sm text-[var(--vbase-red)]">
          {invalid}
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-[var(--vbase-slate500)]">
          Edit any field below. Unset fields are sent as blank so the record matches what you type.
        </p>
        {hasChanges && (
          <span className="text-xs text-[var(--vbase-indigo)]">{computeChanges().length} field(s) changed</span>
        )}
      </div>
      {/* Identity */}
      <div className="grid gap-4 md:grid-cols-3">
        <FieldRow label="First name">
          <input
            type="text"
            value={draft.first_name || ""}
            onChange={(e) => setValue("first_name", e.target.value || undefined)}
            className="vbase-input h-9 w-full"
            disabled={saving || deleting}
          />
        </FieldRow>
        <FieldRow label="Last name">
          <input
            type="text"
            value={draft.last_name || ""}
            onChange={(e) => setValue("last_name", e.target.value || undefined)}
            className="vbase-input h-9 w-full"
            disabled={saving || deleting}
          />
        </FieldRow>
        <FieldRow label="Full name" note="Auto-derived from first/last, but editable.">
          <input
            type="text"
            value={draft.full_name || ""}
            onChange={(e) => setValue("full_name", e.target.value || undefined)}
            className="vbase-input h-9 w-full"
            disabled={saving || deleting}
          />
        </FieldRow>
      </div>

      {/* Role */}
      <div className="grid gap-4 md:grid-cols-3">
        <FieldRow label="Job title">
          <input
            type="text"
            value={draft.job_title || ""}
            onChange={(e) => setValue("job_title", e.target.value || undefined)}
            className="vbase-input h-9 w-full"
            disabled={saving || deleting}
          />
        </FieldRow>
        <FieldRow label="Department">
          <input
            type="text"
            value={draft.department || ""}
            onChange={(e) => setValue("department", e.target.value || undefined)}
            className="vbase-input h-9 w-full"
            disabled={saving || deleting}
          />
        </FieldRow>
        <FieldRow label="Seniority">
          <input
            type="text"
            value={draft.seniority || ""}
            onChange={(e) => setValue("seniority", e.target.value || undefined)}
            className="vbase-input h-9 w-full"
            disabled={saving || deleting}
          />
        </FieldRow>
      </div>

      {/* Reachability */}
      <div className="grid gap-4 md:grid-cols-2">
        <FieldRow label="Email">
          <input
            type="email"
            value={draft.email || ""}
            onChange={(e) => setValue("email", e.target.value || undefined)}
            className="vbase-input h-9 w-full"
            disabled={saving || deleting}
          />
        </FieldRow>
        <FieldRow label="Email status">
          <select
            value={draft.email_status || ""}
            onChange={(e) => setValue("email_status", e.target.value || undefined)}
            className="vbase-input h-9 w-full"
            disabled={saving || deleting}
          >
            {EMAIL_STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </FieldRow>
        <FieldRow label="Phone">
          <input
            type="tel"
            value={draft.phone || ""}
            onChange={(e) => setValue("phone", e.target.value || undefined)}
            className="vbase-input h-9 w-full"
            disabled={saving || deleting}
          />
        </FieldRow>
        <FieldRow label="Phone status">
          <select
            value={draft.phone_status || ""}
            onChange={(e) => setValue("phone_status", e.target.value || undefined)}
            className="vbase-input h-9 w-full"
            disabled={saving || deleting}
          >
            {PHONE_STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </FieldRow>
        <FieldRow label="LinkedIn">
          <input
            type="url"
            value={draft.linkedin_url || ""}
            onChange={(e) => setValue("linkedin_url", e.target.value || undefined)}
            className="vbase-input h-9 w-full"
            disabled={saving || deleting}
          />
        </FieldRow>
      </div>

      {/* Company linkage */}
      <div className="grid gap-4 md:grid-cols-2">
        <FieldRow label="Company" note="Leave blank to unlink.">
          <input
            type="text"
            value={draft.company_name || ""}
            onChange={(e) => setValue("company_name", e.target.value || undefined)}
            className="vbase-input h-9 w-full"
            disabled={saving || deleting}
          />
        </FieldRow>
        <FieldRow label="Linked company">
          <span className="text-sm text-[var(--vbase-slate700)]">
            {company ? (
              <>
                <span className="font-medium">{company.name}</span>
                <span className="text-[var(--vbase-slate500)] ml-1">(id {company.id})</span>
              </>
            ) : (
              <span className="text-[var(--vbase-slate400)]">Not linked</span>
            )}
          </span>
        </FieldRow>
      </div>

      {/* Location */}
      <div className="grid gap-4 md:grid-cols-2">
        <FieldRow label="City">
          <input
            type="text"
            value={draft.city || ""}
            onChange={(e) => setValue("city", e.target.value || undefined)}
            className="vbase-input h-9 w-full"
            disabled={saving || deleting}
          />
        </FieldRow>
        <FieldRow label="Country">
          <input
            type="text"
            value={draft.country || ""}
            onChange={(e) => setValue("country", e.target.value || undefined)}
            className="vbase-input h-9 w-full"
            disabled={saving || deleting}
          />
        </FieldRow>
      </div>

      {/* Enrichment */}
      <div className="grid gap-4 md:grid-cols-2">
        <FieldRow label="Skills" note="Comma separated.">
          <input
            type="text"
            value={draft.skills.join(", ")}
            onChange={(e) => {
              const raw = e.target.value;
              setValue(
                "skills",
                raw
                  ? raw
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean)
                  : []
              );
            }}
            className="vbase-input h-9 w-full"
            disabled={saving || deleting}
          />
        </FieldRow>
        <FieldRow label="Source">
          <input
            type="text"
            value={draft.source || ""}
            onChange={(e) => setValue("source", e.target.value || undefined)}
            className="vbase-input h-9 w-full"
            disabled={saving || deleting}
          />
        </FieldRow>
      </div>

      <FieldRow label="Employment history" note="One per line: Company, Job title, Start, End.">
        <textarea
          rows={3}
          value={draft.employment_history
            .map((e) => [e.company_name, e.job_title, e.start_date, e.end_date].filter(Boolean).join(", "))
            .join("\n")}
          onChange={(e) => {
            const raw = e.target.value;
            const items =
              raw
                .split("\n")
                .map((line) => line.trim())
                .filter(Boolean)
                .map((line) => {
                  const parts = line.split(",").map((s) => s.trim());
                  return {
                    company_name: parts[0] || undefined,
                    job_title: parts[1] || undefined,
                    start_date: parts[2] || undefined,
                    end_date: parts[3] || undefined,
                  };
                });
            setValue("employment_history", items);
          }}
          className="vbase-input w-full resize-y"
          disabled={saving || deleting}
        />
      </FieldRow>

      <FieldRow label="Source">
        <input
          type="text"
          value={draft.source || ""}
          onChange={(e) => setValue("source", e.target.value || undefined)}
          className="vbase-input h-9 w-full"
          disabled={saving || deleting}
        />
      </FieldRow>

      <FieldRow label="Notes">
        <textarea
          rows={4}
          value={draft.notes || ""}
          onChange={(e) => setValue("notes", e.target.value || undefined)}
          className="vbase-input w-full resize-y"
          disabled={saving || deleting}
        />
      </FieldRow>

      <FieldRow label="Stage">
        <select
          value={draft.stage || "New"}
          onChange={(e) => setValue("stage", e.target.value)}
          className="vbase-input h-9 w-full"
          disabled={saving || deleting}
        >
          {STAGE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </FieldRow>

      <FieldRow label="Last verified">
        <input
          type="datetime-local"
          value={draft.last_verified ? draft.last_verified.slice(0, 16) : ""}
          onChange={(e) => setValue("last_verified", e.target.value ? new Date(e.target.value) : undefined)}
          className="vbase-input h-9 w-full"
          disabled={saving || deleting}
        />
      </FieldRow>

      <div className="flex flex-wrap items-center gap-3 border-t border-[var(--vbase-border)] pt-4">
        {hasChanges && !saving && !deleting && (
          <>
            <button
              onClick={save}
              className="vbase-btn-primary flex items-center gap-1.5"
              disabled={saving}
            >
              Save changes
            </button>
            <button
              onClick={fillFromDraft}
              className="vbase-btn-ghost text-sm"
              disabled={saving}
            >
              Discard
            </button>
          </>
        )}
        {!hasChanges && !saving && !deleting && (
          <span className="text-sm text-[var(--vbase-slate500)]">No changes</span>
        )}
        {saving && <span className="text-sm text-[var(--vbase-slate500)]">Saving…</span>}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--vbase-border)] pt-4">
        <div className="flex items-center gap-2">
          {archived ? (
            <button
              onClick={handleRestore}
              disabled={saving || deleting}
              className="vbase-btn-secondary flex items-center gap-1.5 text-sm"
            >
              Restore
            </button>
          ) : (
            <button
              onClick={handleArchive}
              disabled={saving || deleting}
              className="vbase-btn-ghost flex items-center gap-1.5 text-sm text-[var(--vbase-amber)]"
            >
              Archive
            </button>
          )}
          <span className="text-xs text-[var(--vbase-slate500)]">
            {archived ? "Archived" : "Active"}
          </span>
        </div>
        <button
          onClick={handleDelete}
          disabled={saving || deleting || archived}
          className="vbase-btn-danger flex items-center gap-1.5 text-sm"
        >
          Delete
        </button>
      </div>
    </div>
  );
}
