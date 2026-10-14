import { useState, useEffect, useCallback } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  IconSparkle,
  IconBuilding2,
  IconMapPin,
  IconMail,
  IconLink,
  IconGlobe,
  IconTag,
  IconFileText,
  IconClock,
  IconTarget,
  IconPencil,
  IconArchive,
  IconTrash2,
  IconExternalLink,
  IconArrowRightLeft,
  IconArrowLeft,
  IconUsers,
} from "@/lib/icons";
import { api } from "@/lib/api";
import { Lead, LeadConversion, Contact, Company } from "@/lib/types";
import { ContactAvatar } from "@/components/crm";
import { LeadEditor, ScorePanel } from "@/components/crm";
import { CRM_STAGES, parsePhone } from "@/lib/crm";
import { toast } from "@/lib/store";

export function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [lead, setLead] = useState<Lead | null>(null);
  const [contact, setContact] = useState<Contact | null>(null);
  const [company, setCompany] = useState<Company | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [converting, setConverting] = useState(false);

  const load = useCallback(async (leadId: string) => {
    const data = await api.get<Lead>(`/leads/${leadId}`);
    setLead(data);
    // A converted lead links to a real contact; load it so the panel shows the
    // durable record rather than just an id.
    if (data.converted_contact_id) {
      api
        .get<Contact>(`/contacts/${data.converted_contact_id}`)
        .then(setContact)
        .catch(() => setContact(null));
    } else {
      setContact(null);
    }
    if (data.converted_company_id) {
      api
        .get<Company>(`/companies/${data.converted_company_id}`)
        .then(setCompany)
        .catch(() => setCompany(null));
    } else {
      setCompany(null);
    }
  }, []);

  useEffect(() => {
    if (!id || isNaN(Number(id))) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        await load(id);
      } catch (e: any) {
        if (!cancelled) toast(e?.data?.detail || "Lead not found", "error");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, load]);

  if (loading) {
    return (
      <div className="flex flex-col gap-3">
        <div className="h-8 w-56 rounded bg-[var(--vbase-slate200)]" />
        <div className="h-8 w-80 rounded bg-[var(--vbase-slate200)]" />
      </div>
    );
  }

  if (!lead) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center text-sm text-[var(--vbase-slate500)]">
        <IconSparkle className="h-8 w-8" />
        Lead not found
        <Link to="/leads" className="vbase-btn-secondary flex items-center gap-1.5 text-sm">
          <IconArrowLeft className="h-4 w-4" />
          Back to leads
        </Link>
      </div>
    );
  }

  const name = lead.display_name || lead.full_name || lead.email || "Lead";

  const toggleArchive = async () => {
    try {
      const updated = await api.post<Lead>(`/leads/${lead.id}/${lead.is_archived ? "restore" : "archive"}`);
      setLead(updated);
      toast(updated.is_archived ? "Lead archived" : "Lead restored", "success");
    } catch (e: any) {
      toast(e?.data?.detail || "Could not update archive state", "error");
    }
  };

  const removeLead = async () => {
    if (!window.confirm("Delete this lead? This cannot be undone.")) return;
    try {
      await api.delete(`/leads/${lead.id}`);
      toast("Lead deleted", "success");
      navigate("/leads");
    } catch (e: any) {
      toast(e?.data?.detail || "Delete failed", "error");
    }
  };

  if (editing) {
    return (
      <div className="flex flex-col gap-6">
        <LeadHeader lead={lead} name={name} />
        <LeadEditor
          lead={lead}
          onSaved={async (updated) => {
            setLead(updated);
            if (id) await load(id).catch(() => undefined);
          }}
          onDelete={() => navigate("/leads")}
          onConvert={() => {
            setEditing(false);
            setConverting(true);
          }}
          onCancel={() => setEditing(false)}
        />
        <button onClick={() => setEditing(false)} className="vbase-btn-ghost self-start text-sm">
          Back to details
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <LeadHeader lead={lead} name={name} />

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setEditing(true)}
          className="vbase-btn-primary flex items-center gap-1.5 text-sm"
        >
          <IconPencil className="h-4 w-4" />
          Edit record
        </button>
        <Link to={`/leads/${lead.id}/edit`} className="vbase-btn-secondary flex items-center gap-1.5 text-sm">
          <IconExternalLink className="h-4 w-4" />
          Open full editor
        </Link>
        {!lead.converted_at && (
          <button
            onClick={() => setConverting(true)}
            className="vbase-btn-secondary flex items-center gap-1.5 text-sm"
          >
            <IconArrowRightLeft className="h-4 w-4" />
            Convert to contact
          </button>
        )}
        <button
          onClick={toggleArchive}
          className="vbase-btn-ghost flex items-center gap-1.5 text-sm text-[var(--vbase-amber)]"
        >
          <IconArchive className="h-4 w-4" />
          {lead.is_archived ? "Restore" : "Archive"}
        </button>
        <button onClick={removeLead} className="vbase-btn-danger flex items-center gap-1.5 text-sm">
          <IconTrash2 className="h-4 w-4" />
          Delete
        </button>
      </div>

      {converting && (
        <ConvertDialog
          lead={lead}
          onClose={() => setConverting(false)}
          onConverted={async (result) => {
            setConverting(false);
            setLead(result.lead);
            setContact(result.contact);
            setCompany(result.company);
            if (id) await load(id).catch(() => undefined);
          }}
        />
      )}

      {lead.converted_at && (
        <div className="vbase-card border-[var(--vbase-green)]/30 bg-[var(--vbase-green)]/5 p-4">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-[var(--vbase-slate800)]">
            <IconUsers className="h-4 w-4" />
            Converted {new Date(lead.converted_at).toLocaleString()}
          </h3>
          <p className="mt-1 text-xs text-[var(--vbase-slate600)]">
            This lead became a durable record. Edit the contact or company from here — the lead keeps the trail.
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {contact && (
              <Link to={`/contacts/${contact.id}`} className="vbase-btn-secondary flex items-center gap-1.5 text-sm">
                <IconUsers className="h-4 w-4" />
                {contact.display_name || contact.full_name || contact.email}
              </Link>
            )}
            {company && (
              <Link to={`/companies/${company.id}`} className="vbase-btn-secondary flex items-center gap-1.5 text-sm">
                <IconBuilding2 className="h-4 w-4" />
                {company.name}
              </Link>
            )}
          </div>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <ScorePanel lead={lead} />

        <DetailCard title="Contact details" icon={<IconMail className="h-4 w-4" />}>
          <Field label="Email" value={lead.email} href={lead.email ? `mailto:${lead.email}` : undefined} />
          <Field label="Email status" value={lead.email_status} />
          <Field
            label="Phone"
            value={parsePhone(lead.phone)?.display ?? lead.phone}
            href={lead.phone ? `tel:${lead.phone}` : undefined}
          />
          <Field label="Phone status" value={lead.phone_status} />
          <Field label="LinkedIn" value={lead.linkedin_url} href={lead.linkedin_url || undefined} />
        </DetailCard>

        <DetailCard title="Company" icon={<IconBuilding2 className="h-4 w-4" />}>
          {lead.company_id ? (
            <Link
              to={`/companies/${lead.company_id}`}
              className="flex items-center gap-1.5 text-sm font-medium text-[var(--vbase-indigo)] hover:underline"
            >
              <IconBuilding2 className="h-4 w-4" />
              {lead.company_name || company?.name || `Company ${lead.company_id}`}
              <IconExternalLink className="h-3.5 w-3.5" />
            </Link>
          ) : (
            <Field label="Company" value={lead.company_name} />
          )}
          <Field label="Domain" value={lead.company_domain} />
          <Field label="Industry" value={lead.industry} />
          <Field label="Employees" value={lead.employee_count != null ? String(lead.employee_count) : null} />
          <Field label="Size band" value={lead.company_size} />
          <Field label="Website" value={lead.website} href={lead.website || undefined} />
        </DetailCard>

        <DetailCard title="Location" icon={<IconMapPin className="h-4 w-4" />}>
          <Field label="City" value={lead.city} />
          <Field label="State" value={lead.state} />
          <Field label="Country" value={lead.country} />
        </DetailCard>

        <DetailCard title="Attribution" icon={<IconGlobe className="h-4 w-4" />}>
          <Field label="Lead source" value={lead.lead_source} />
          <Field label="Campaign" value={lead.campaign} />
          <Field label="Priority" value={lead.priority} />
          <Field label="Status" value={lead.lead_status} />
        </DetailCard>

        <DetailCard title="Follow-up" icon={<IconClock className="h-4 w-4" />}>
          {lead.next_follow_up_at ? (
            <p
              className={
                new Date(lead.next_follow_up_at).getTime() < Date.now()
                  ? "text-sm font-medium text-[var(--vbase-red)]"
                  : "text-sm text-[var(--vbase-slate800)]"
              }
            >
              {new Date(lead.next_follow_up_at).toLocaleString()}
              {new Date(lead.next_follow_up_at).getTime() < Date.now() && " · overdue"}
            </p>
          ) : (
            <p className="text-sm text-[var(--vbase-slate400)]">No follow-up scheduled</p>
          )}
          <Field label="Communication preference" value={lead.consent_status} />
          {lead.do_not_contact && (
            <p className="mt-1 rounded-md border border-[var(--vbase-red)]/30 bg-[var(--vbase-red)]/5 px-2.5 py-1.5 text-xs text-[var(--vbase-red)]">
              This prospect asked not to be contacted. Outreach is suppressed.
            </p>
          )}
          {lead.disqualified_reason && <Field label="Disqualification reason" value={lead.disqualified_reason} />}
        </DetailCard>

        <DetailCard title="Tags" icon={<IconTag className="h-4 w-4" />}>
          {lead.tag_names && lead.tag_names.length ? (
            <div className="flex flex-wrap gap-1.5">
              {lead.tag_names.map((tag) => (
                <span key={tag} className="vbase-chip">
                  {tag}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[var(--vbase-slate400)]">No tags</p>
          )}
        </DetailCard>

        <DetailCard title="Record" icon={<IconTarget className="h-4 w-4" />}>
          <Field label="Data quality" value={`${lead.data_quality_score} / 100`} />
          <Field label="Created" value={lead.created_at ? new Date(lead.created_at).toLocaleString() : null} />
          <Field label="Updated" value={lead.updated_at ? new Date(lead.updated_at).toLocaleString() : null} />
        </DetailCard>
      </div>

      <DetailCard title="Notes" icon={<IconFileText className="h-4 w-4" />}>
        {lead.notes ? (
          <p className="whitespace-pre-wrap text-sm text-[var(--vbase-slate700)]">{lead.notes}</p>
        ) : (
          <p className="text-sm text-[var(--vbase-slate400)]">No notes yet.</p>
        )}
      </DetailCard>
    </div>
  );
}

function LeadHeader({ lead, name }: { lead: Lead; name: string }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex items-start gap-4">
        <ContactAvatar name={name} size={56} />
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold text-[var(--vbase-slate900)]">{name}</h1>
            <span className="inline-flex items-center rounded-full border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-2.5 py-0.5 text-xs font-medium text-[var(--vbase-slate600)]">
              {lead.lifecycle_stage}
            </span>
            {lead.is_archived && (
              <span className="inline-flex items-center rounded-full border border-[var(--vbase-border)] bg-[var(--vbase-slate100)] px-2.5 py-0.5 text-xs font-medium uppercase tracking-wide text-[var(--vbase-slate500)]">
                Archived
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-[var(--vbase-slate500)]">
            {[lead.job_title, lead.company_name, [lead.city, lead.country].filter(Boolean).join(", ")]
              .filter(Boolean)
              .join(" · ") || "No role, company or location recorded yet"}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-3 py-1.5 text-sm font-semibold text-[var(--vbase-slate800)]">
          <IconTarget className="h-4 w-4 text-[var(--vbase-indigo)]" />
          {lead.lead_score}
          <span className="text-xs font-normal text-[var(--vbase-slate500)]">/100</span>
        </span>
      </div>
    </div>
  );
}

function DetailCard({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="vbase-card p-4">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-[var(--vbase-slate800)]">
        {icon}
        {title}
      </h3>
      <div className="space-y-2.5">{children}</div>
    </div>
  );
}

function Field({ label, value, href }: { label: string; value?: string | null; href?: string }) {
  return (
    <div className="flex items-baseline gap-2 text-sm">
      <span className="w-32 flex-shrink-0 text-xs text-[var(--vbase-slate500)]">{label}</span>
      {value ? (
        href ? (
          <a
            href={href}
            target={href.startsWith("http") ? "_blank" : undefined}
            rel="noreferrer"
            className="flex min-w-0 items-center gap-1 text-[var(--vbase-indigo)] hover:underline"
          >
            <span className="truncate">{value}</span>
            <IconLink className="h-3 w-3 flex-shrink-0" />
          </a>
        ) : (
          <span className="min-w-0 truncate text-[var(--vbase-slate800)]" title={value}>
            {value}
          </span>
        )
      ) : (
        <span className="text-[var(--vbase-slate400)]">—</span>
      )}
    </div>
  );
}

/** Conversion dialog.
 *
 * The modes mirror the API contract exactly: auto matches then creates, link
 * requires an existing record, create refuses when a match already exists. That
 * is what stops a conversion from producing a duplicate person or company.
 */
function ConvertDialog({
  lead,
  onClose,
  onConverted,
}: {
  lead: Lead;
  onClose: () => void;
  onConverted: (result: LeadConversion) => void;
}) {
  const [contactMode, setContactMode] = useState<"auto" | "create" | "link">("auto");
  const [contactId, setContactId] = useState("");
  const [companyMode, setCompanyMode] = useState<"auto" | "create" | "link" | "none">("auto");
  const [companyId, setCompanyId] = useState("");
  const [contactStage, setContactStage] = useState("New");
  const [fillMissing, setFillMissing] = useState(true);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        contact_mode: contactMode,
        company_mode: companyMode,
        contact_stage: contactStage,
        fill_missing_fields: fillMissing,
      };
      if (contactMode === "link" && contactId.trim()) body.contact_id = Number(contactId.trim());
      if (companyMode === "link" && companyId.trim()) body.company_id = Number(companyId.trim());
      if (note.trim()) body.note = note.trim();

      const result = await api.post<LeadConversion>(`/leads/${lead.id}/convert`, body);
      toast(
        result.created_contact
          ? `Converted — created contact #${result.contact.id}`
          : `Converted — linked to existing contact #${result.contact.id}`,
        "success",
      );
      onConverted(result);
    } catch (e: any) {
      const detail = e?.data?.detail;
      setError(Array.isArray(detail) ? detail.map((d: any) => d?.msg || "Invalid").join("; ") : detail || e?.message || "Conversion failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="vbase-card space-y-4 p-4">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-[var(--vbase-slate800)]">
          <IconArrowRightLeft className="h-4 w-4" />
          Convert this lead
        </h3>
        <button onClick={onClose} className="vbase-btn-ghost text-sm" disabled={busy}>
          Cancel
        </button>
      </div>

      {error && (
        <div role="alert" className="rounded-md border border-[var(--vbase-red)]/30 bg-[var(--vbase-red)]/5 p-3 text-sm text-[var(--vbase-red)]">
          {error}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <label className="text-xs font-medium text-[var(--vbase-slate500)]">Contact</label>
          <select
            value={contactMode}
            onChange={(e) => setContactMode(e.target.value as typeof contactMode)}
            className="vbase-input mt-1 h-9 w-full"
            disabled={busy}
          >
            <option value="auto">Match by email, otherwise create</option>
            <option value="create">Always create (refuses if a match exists)</option>
            <option value="link">Link to an existing contact</option>
          </select>
          {contactMode === "link" && (
            <input
              type="number"
              value={contactId}
              onChange={(e) => setContactId(e.target.value)}
              placeholder="Existing contact id"
              aria-label="Existing contact id"
              className="vbase-input mt-2 h-9 w-full"
              disabled={busy}
            />
          )}
          <p className="mt-1 text-[11px] text-[var(--vbase-slate500)]">
            A contact with the same email is linked, never duplicated.
          </p>
        </div>

        <div>
          <label className="text-xs font-medium text-[var(--vbase-slate500)]">Company</label>
          <select
            value={companyMode}
            onChange={(e) => setCompanyMode(e.target.value as typeof companyMode)}
            className="vbase-input mt-1 h-9 w-full"
            disabled={busy}
          >
            <option value="auto">Match by name or domain, otherwise create</option>
            <option value="create">Always create (refuses if a match exists)</option>
            <option value="link">Link to an existing company</option>
            <option value="none">Do not link a company</option>
          </select>
          {companyMode === "link" && (
            <input
              type="number"
              value={companyId}
              onChange={(e) => setCompanyId(e.target.value)}
              placeholder="Existing company id"
              aria-label="Existing company id"
              className="vbase-input mt-2 h-9 w-full"
              disabled={busy}
            />
          )}
          <p className="mt-1 text-[11px] text-[var(--vbase-slate500)]">
            Source: {lead.company_name || "not recorded"}
            {lead.company_domain ? ` · ${lead.company_domain}` : ""}
          </p>
        </div>

        <div>
          <label className="text-xs font-medium text-[var(--vbase-slate500)]">Contact stage</label>
          <select
            value={contactStage}
            onChange={(e) => setContactStage(e.target.value)}
            className="vbase-input mt-1 h-9 w-full"
            disabled={busy}
          >
            {CRM_STAGES.map((stage) => (
              <option key={stage} value={stage}>
                {stage}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-start gap-2 pt-5">
          <input
            id="fill-missing"
            type="checkbox"
            checked={fillMissing}
            onChange={(e) => setFillMissing(e.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-[var(--vbase-border)] text-[var(--vbase-indigo)]"
            disabled={busy}
          />
          <label htmlFor="fill-missing" className="text-xs text-[var(--vbase-slate600)]">
            Copy this lead's values into blank fields on the contact and company.
            <span className="block text-[11px] text-[var(--vbase-slate400)]">
              Existing values are never overwritten.
            </span>
          </label>
        </div>
      </div>

      <div>
        <label className="text-xs font-medium text-[var(--vbase-slate500)]">Note (optional)</label>
        <textarea
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Why is this lead being converted now?"
          className="vbase-input mt-1 w-full resize-y"
          disabled={busy}
        />
      </div>

      <div className="flex items-center gap-2 border-t border-[var(--vbase-border)] pt-3">
        <button onClick={submit} className="vbase-btn-primary" disabled={busy}>
          {busy ? "Converting…" : "Convert lead"}
        </button>
        <span className="text-xs text-[var(--vbase-slate500)]">
          The lead keeps its history and records the link to the new records.
        </span>
      </div>
    </div>
  );
}
