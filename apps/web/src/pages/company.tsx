import { useState, useEffect } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  IconBuilding2,
  IconMapPin,
  IconTag,
  IconUsers,
  IconLink,
  IconGlobe,
  IconCalendar,
  IconCpu,
  IconFileText,
  IconClock,
  IconMail,
  IconExternalLink,
  IconArrowRight,
  IconPencil,
  IconArchive,
  IconTrash2,
} from "@/lib/icons";
import { api } from "@/lib/api";
import { Company, Contact } from "@/lib/types";
import { ContactAvatar, CompanyEditor } from "@/components/crm";
import { toast } from "@/lib/store";


export function CompanyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [company, setCompany] = useState<Company | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (!id || isNaN(Number(id))) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    const load = async () => {
      try {
        const c = await api.get<Company>(`/companies/${id}`);
        if (cancelled) return;
        setCompany(c);
        try {
          const co = await api.get<{ items: Contact[] }>("/contacts", {
            params: { company_name: c.name, page_size: 100 },
          });
          if (!cancelled) setContacts(co.items || []);
        } catch {
          if (!cancelled) setContacts([]);
        }
      } catch (e) {
        console.error(e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading && !company) {
    return (
      <div className="flex flex-col gap-4">
        <div className="h-8 w-64 rounded bg-[var(--vbase-slate200)]" />
        <div className="h-24 rounded-lg bg-[var(--vbase-slate200)]" />
      </div>
    );
  }

  if (!company) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center text-sm text-[var(--vbase-slate500)]">
        <IconBuilding2 className="h-8 w-8" />
        Company not found
      </div>
    );
  }

  const toggleArchive = async () => {
    try {
      const updated = await api.post<Company>(
        `/companies/${company.id}/${company.is_archived ? "restore" : "archive"}`,
      );
      setCompany(updated);
      toast(updated.is_archived ? "Company archived" : "Company restored", "success");
    } catch (e: any) {
      toast(e?.data?.detail || "Could not update archive state", "error");
    }
  };

  const removeCompany = async () => {
    if (!window.confirm(`Delete ${company.name}? Linked contacts are kept but detached. This cannot be undone.`)) {
      return;
    }
    try {
      await api.delete(`/companies/${company.id}`);
      toast("Company deleted", "success");
      navigate("/companies");
    } catch (e: any) {
      toast(e?.data?.detail || "Delete failed", "error");
    }
  };

  if (editing) {
    return (
      <div className="flex flex-col gap-6">
        <CompanyHeader company={company} />
        <CompanyEditor
          company={company}
          onSaved={(updated) => setCompany(updated)}
          onDelete={() => navigate("/companies")}
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
      <CompanyHeader company={company} />

      <div className="flex flex-wrap items-center gap-2">
        <button onClick={() => setEditing(true)} className="vbase-btn-primary flex items-center gap-1.5 text-sm">
          <IconPencil className="h-4 w-4" />
          Edit record
        </button>
        <Link to={`/companies/${company.id}/edit`} className="vbase-btn-secondary flex items-center gap-1.5 text-sm">
          <IconExternalLink className="h-4 w-4" />
          Open full editor
        </Link>
        <button
          onClick={toggleArchive}
          className="vbase-btn-ghost flex items-center gap-1.5 text-sm text-[var(--vbase-amber)]"
        >
          <IconArchive className="h-4 w-4" />
          {company.is_archived ? "Restore" : "Archive"}
        </button>
        <button onClick={removeCompany} className="vbase-btn-danger flex items-center gap-1.5 text-sm">
          <IconTrash2 className="h-4 w-4" />
          Delete
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <AttributeCard
          icon={<IconGlobe className="h-4 w-4" />}
          label="Website"
          value={
            company.website ? (
              <a
                href={company.website}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 text-sm text-[var(--vbase-indigo)] hover:underline"
              >
                {company.website}
                <IconExternalLink className="h-3.5 w-3.5" />
              </a>
            ) : (
              <span className="text-sm text-[var(--vbase-slate400)]">—</span>
            )
          }
        />
        <AttributeCard
          icon={<IconLink className="h-4 w-4" />}
          label="LinkedIn"
          value={
            company.linkedin_url ? (
              <a
                href={company.linkedin_url}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 text-sm text-[var(--vbase-indigo)] hover:underline"
              >
                Company page
                <IconExternalLink className="h-3.5 w-3.5" />
              </a>
            ) : (
              <span className="text-sm text-[var(--vbase-slate400)]">—</span>
            )
          }
        />
        <AttributeCard
          icon={<IconMapPin className="h-4 w-4" />}
          label="Headquarters"
          value={
            company.headquarters || company.city || company.country ? (
              <div className="text-sm">
                {(company.headquarters || company.city) && (
                  <span className="text-[var(--vbase-slate800)] block">
                    {company.headquarters || company.city}
                  </span>
                )}
                {company.country && (
                  <span className="text-xs text-[var(--vbase-slate500)]">{company.country}</span>
                )}
              </div>
            ) : (
              <span className="text-sm text-[var(--vbase-slate400)]">—</span>
            )
          }
        />
        <AttributeCard
          icon={<IconUsers className="h-4 w-4" />}
          label="Size"
          value={
            company.employee_count != null ? (
              <span className="text-sm text-[var(--vbase-slate800)]">
                {company.employee_count.toLocaleString()} employees
              </span>
            ) : company.company_size ? (
              <span className="text-sm text-[var(--vbase-slate800)]">{company.company_size}</span>
            ) : (
              <span className="text-sm text-[var(--vbase-slate400)]">—</span>
            )
          }
        />
        <AttributeCard
          icon={<IconBuilding2 className="h-4 w-4" />}
          label="Sub-industry"
          value={
            company.sub_industry ? (
              <span className="text-sm text-[var(--vbase-slate800)]">{company.sub_industry}</span>
            ) : (
              <span className="text-sm text-[var(--vbase-slate400)]">—</span>
            )
          }
        />
        <AttributeCard
          icon={<IconMapPin className="h-4 w-4" />}
          label="State"
          value={
            company.state ? (
              <span className="text-sm text-[var(--vbase-slate800)]">{company.state}</span>
            ) : (
              <span className="text-sm text-[var(--vbase-slate400)]">—</span>
            )
          }
        />
        <AttributeCard
          icon={<IconArrowRight className="h-4 w-4" />}
          label="Account status"
          value={
            company.company_status ? (
              <span className="text-sm text-[var(--vbase-slate800)]">{company.company_status}</span>
            ) : (
              <span className="text-sm text-[var(--vbase-slate400)]">—</span>
            )
          }
        />
        <AttributeCard
          icon={<IconCalendar className="h-4 w-4" />}
          label="Founded"
          value={company.founded_year ? <span className="text-sm text-[var(--vbase-slate800)]">{company.founded_year}</span> : <span className="text-sm text-[var(--vbase-slate400)]">—</span>}
        />
        <AttributeCard
          icon={<IconTag className="h-4 w-4" />}
          label="Funding stage"
          value={
            company.funding_stage ? (
              <span className="text-sm text-[var(--vbase-slate800)]">{company.funding_stage}</span>
            ) : (
              <span className="text-sm text-[var(--vbase-slate400)]">—</span>
            )
          }
        />
        <AttributeCard
          icon={<IconCpu className="h-4 w-4" />}
          label="Technologies"
          value={
            company.technologies.length ? (
              <div className="flex flex-wrap gap-1.5">
                {company.technologies.map((t) => (
                  <span key={t} className="vbase-chip">
                    {t}
                  </span>
                ))}
              </div>
            ) : (
              <span className="text-sm text-[var(--vbase-slate400)]">—</span>
            )
          }
        />
        <AttributeCard
          icon={<IconFileText className="h-4 w-4" />}
          label="Source"
          value={<span className="text-sm text-[var(--vbase-slate800)]">{company.source || "Manual"}</span>}
        />
        <AttributeCard
          icon={<IconClock className="h-4 w-4" />}
          label="Last verified"
          value={
            company.last_verified ? (
              <span className="text-sm text-[var(--vbase-slate800)]">
                {new Date(company.last_verified).toLocaleString()}
              </span>
            ) : (
              <span className="text-sm text-[var(--vbase-slate400)]">Never</span>
            )
          }
        />
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <SectionCard label="Tags" icon={<IconTag className="h-4 w-4" />}>
          {company.tag_names && company.tag_names.length ? (
            <div className="flex flex-wrap gap-1.5">
              {company.tag_names.map((t) => (
                <TagChip key={t} name={t} />
              ))}
            </div>
          ) : (
            <p className="text-sm text-[var(--vbase-slate400)]">No tags</p>
          )}
        </SectionCard>

        <SectionCard label="Notes" icon={<IconFileText className="h-4 w-4" />}>
          {company.notes ? (
            <p className="text-sm text-[var(--vbase-slate700)] whitespace-pre-wrap">{company.notes}</p>
          ) : (
            <p className="text-sm text-[var(--vbase-slate400)]">No notes</p>
          )}
        </SectionCard>
      </div>

      <ContactsSection company={company} contacts={contacts} />
    </div>
  );
}

function CompanyHeader({ company }: { company: Company }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex items-start gap-4">
        <div className="mt-1 flex h-14 w-14 items-center justify-center rounded-full bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]">
          <IconBuilding2 className="h-7 w-7" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-2xl font-semibold text-[var(--vbase-slate900)]">{company.name}</h1>
            <DomainChip domain={company.domain} />
          </div>
          <p className="mt-1 text-sm text-[var(--vbase-slate500)]">
            {company.industry || "Unknown industry"}
            {company.domain ? ` · ${company.domain}` : ""}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <QualityChip score={company.data_quality_score} />
        <Link
          to={`/contacts?company_name=${encodeURIComponent(company.name)}`}
          className="inline-flex items-center gap-1 rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-3 py-1.5 text-sm font-medium text-[var(--vbase-slate700)] transition-colors hover:border-[var(--vbase-indigo)] hover:text-[var(--vbase-indigo)]"
        >
          <IconUsers className="h-4 w-4" />
          Contacts
          <IconArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </div>
  );
}

function DomainChip({ domain }: { domain?: string | null }) {
  if (!domain) return null;
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-2 py-0.5 text-xs font-medium text-[var(--vbase-slate600)]">
      <IconGlobe className="h-3 w-3" />
      {domain}
    </span>
  );
}

function QualityChip({ score }: { score: number }) {
  const rank = score >= 70 ? "high" : score >= 40 ? "medium" : "low";
  const colors = {
    high: "inline-flex items-center rounded-full border border-[var(--vbase-green)]/30 bg-[var(--vbase-green)]/10 px-2.5 py-1 text-xs font-semibold text-[var(--vbase-green)]",
    medium: "inline-flex items-center rounded-full border border-[var(--vbase-amber)]/30 bg-[var(--vbase-amber)]/10 px-2.5 py-1 text-xs font-semibold text-[var(--vbase-amber)]",
    low: "inline-flex items-center rounded-full border border-[var(--vbase-red)]/30 bg-[var(--vbase-red)]/10 px-2.5 py-1 text-xs font-semibold text-[var(--vbase-red)]",
  };
  return (
    <span className={colors[rank]}>
      {score} / 100
    </span>
  );
}

function AttributeCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] p-4">
      <div className="mt-0.5 flex h-7 w-7 items-center justify-center rounded border border-[var(--vbase-border)] bg-[var(--vbase-bg)] text-[var(--vbase-slate500)]">
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-[var(--vbase-slate500)]">{label}</p>
        <div className="mt-1.5">{value}</div>
      </div>
    </div>
  );
}

function SectionCard({ label, icon, children }: { label: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="vbase-card p-4">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-[var(--vbase-slate800)]">
        {icon}
        {label}
      </h3>
      {children}
    </div>
  );
}

function TagChip({ name }: { name: string }) {
  return <span className="vbase-chip">{name}</span>;
}

function ContactsSection({ company, contacts }: { company: Company; contacts: Contact[] }) {
  return (
    <div className="vbase-card">
      <div className="flex items-center justify-between border-b border-[var(--vbase-border)] px-4 py-3">
        <div>
          <h3 className="flex items-center gap-2 font-semibold text-[var(--vbase-slate800)]">
            <IconUsers className="h-4 w-4" />
            Contacts at {company.name}
          </h3>
          <p className="text-xs text-[var(--vbase-slate500)]">{contacts.length} contact{contacts.length !== 1 ? "s" : ""}</p>
        </div>
        <Link
          to={`/contacts?company_name=${encodeURIComponent(company.name)}`}
          className="inline-flex items-center gap-1 rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-3 py-1.5 text-sm text-[var(--vbase-slate600)] transition-colors hover:border-[var(--vbase-indigo)] hover:text-[var(--vbase-indigo)]"
        >
          View all
          <IconArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>

      {contacts.length ? (
        <div className="divide-y divide-[var(--vbase-border)]">
          {contacts.map((contact) => (
            <Link key={contact.id} to={`/contacts/${contact.id}`} className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-[var(--vbase-bg-alt)]">
              <ContactAvatar name={contact.display_name || contact.full_name || contact.email || "Contact"} size={34} />
              <div className="min-w-0 flex-1">
                <p className="font-medium text-[var(--vbase-slate900)] truncate">
                  {contact.display_name || contact.full_name || contact.email || "Contact"}
                </p>
                <p className="text-xs text-[var(--vbase-slate500)] truncate">{contact.job_title || "No job title"}</p>
              </div>
              {contact.email && (
                <span className="hidden items-center gap-1 text-xs text-[var(--vbase-slate500)] md:flex">
                  <IconMail className="h-3 w-3" />
                  {contact.email}
                </span>
              )}
              <IconArrowRight className="h-4 w-4 text-[var(--vbase-slate400)]" />
            </Link>
          ))}
        </div>
      ) : (
        <div className="px-4 py-8 text-center text-sm text-[var(--vbase-slate500)]">
          No contacts linked to this company.
        </div>
      )}
    </div>
  );
}
