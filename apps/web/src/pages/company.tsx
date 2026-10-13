import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { IconBuilding2, IconMapPin, IconTag, IconUsers, IconLink, IconGlobe, IconCalendar, IconCpu, IconFileText, IconClock, IconMail, IconExternalLink } from "@/lib/icons";
import { api } from "@/lib/api";
import { Company, Contact } from "@/lib/types";

function DetailCard({ title, icon, children }: any) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] p-4">
      <div className="mt-0.5 flex h-7 w-7 items-center justify-center rounded border border-[var(--vbase-border)] bg-[var(--vbase-bg)] text-[var(--vbase-slate500)]">{icon}</div>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-[var(--vbase-slate500)]">{title}</p>
        <div className="mt-1">{children}</div>
      </div>
    </div>
  );
}

export function CompanyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [company, setCompany] = useState<Company | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);

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
          const co = await api.get<{ items: Contact[] }>(`/contacts`, { params: { company_name: c.name, page_size: 100 } });
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
    return () => { cancelled = true; };
  }, [id]);

  const qualityClass = company
    ? company.data_quality_score >= 70
      ? "bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]"
      : company.data_quality_score >= 40
        ? "bg-[var(--vbase-amber)]/10 text-[var(--vbase-amber)]"
        : "bg-[var(--vbase-red)]/10 text-[var(--vbase-red)]"
    : "bg-[var(--vbase-slate100)] text-[var(--vbase-slate500)]";

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

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-4">
          <div className="mt-1 flex h-14 w-14 items-center justify-center rounded-full bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]">
            <IconBuilding2 className="h-7 w-7" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-[var(--vbase-slate900)]">{company.name}</h1>
            <p className="mt-1 text-sm text-[var(--vbase-slate500)]">
              {company.industry || "Unknown industry"}
              {company.domain ? ` · ${company.domain}` : ""}
            </p>
          </div>
        </div>
        <div className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${qualityClass}`}>
          {company.data_quality_score} / 100
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <DetailCard title="Website" icon={<IconGlobe className="h-4 w-4" />}>
          {company.website ? (
            <a href={company.website} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-sm text-[var(--vbase-indigo)] hover:underline">
              {company.website}
              <IconExternalLink className="h-3 w-3" />
            </a>
          ) : (
            <p className="text-sm text-[var(--vbase-slate400)]">—</p>
          )}
        </DetailCard>

        <DetailCard title="LinkedIn" icon={<IconLink className="h-4 w-4" />}>
          {company.linkedin_url ? (
            <a href={company.linkedin_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-sm text-[var(--vbase-indigo)] hover:underline">
              Company page
              <IconExternalLink className="h-3 w-3" />
            </a>
          ) : (
            <p className="text-sm text-[var(--vbase-slate400)]">—</p>
          )}
        </DetailCard>

        <DetailCard title="Headquarters" icon={<IconMapPin className="h-4 w-4" />}>
          {company.headquarters || company.city || company.country ? (
            <>
              {(company.headquarters || company.city) && (
                <p className="text-sm text-[var(--vbase-slate800)]">{company.headquarters || company.city}</p>
              )}
              {company.country && <p className="text-xs text-[var(--vbase-slate500)]">{company.country}</p>}
            </>
          ) : (
            <p className="text-sm text-[var(--vbase-slate400)]">—</p>
          )}
        </DetailCard>

        <DetailCard title="Size" icon={<IconUsers className="h-4 w-4" />}>
          {company.employee_count != null ? (
            <p className="text-sm text-[var(--vbase-slate800)]">{company.employee_count.toLocaleString()} employees</p>
          ) : company.company_size ? (
            <p className="text-sm text-[var(--vbase-slate800)]">{company.company_size}</p>
          ) : (
            <p className="text-sm text-[var(--vbase-slate400)]">—</p>
          )}
          {company.company_size && company.employee_count != null && (
            <p className="text-xs text-[var(--vbase-slate500)]">Segment {company.company_size}</p>
          )}
        </DetailCard>

        <DetailCard title="Founded" icon={<IconCalendar className="h-4 w-4" />}>
          {company.founded_year ? (
            <p className="text-sm text-[var(--vbase-slate800)]">{company.founded_year}</p>
          ) : (
            <p className="text-sm text-[var(--vbase-slate400)]">—</p>
          )}
        </DetailCard>

        <DetailCard title="Funding stage" icon={<IconTag className="h-4 w-4" />}>
          {company.funding_stage || company.company_status ? (
            <p className="text-sm text-[var(--vbase-slate800)]">{company.funding_stage || company.company_status}</p>
          ) : (
            <p className="text-sm text-[var(--vbase-slate400)]">—</p>
          )}
        </DetailCard>

        <DetailCard title="Technologies" icon={<IconCpu className="h-4 w-4" />}>
          {company.technologies && company.technologies.length ? (
            <div className="flex flex-wrap gap-1.5">
              {company.technologies.map((t) => (
                <span key={t} className="vbase-chip flex h-7 items-center px-2.5 py-0.5">{t}</span>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[var(--vbase-slate400)]">—</p>
          )}
        </DetailCard>

        <DetailCard title="Source" icon={<IconFileText className="h-4 w-4" />}>
          <p className="text-sm text-[var(--vbase-slate800)]">{company.source || "Manual"}</p>
        </DetailCard>

        <DetailCard title="Last verified" icon={<IconClock className="h-4 w-4" />}>
          {company.last_verified ? (
            <p className="text-sm text-[var(--vbase-slate800)]">{new Date(company.last_verified).toLocaleString()}</p>
          ) : (
            <p className="text-sm text-[var(--vbase-slate400)]">Never</p>
          )}
        </DetailCard>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="vbase-card p-4">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-[var(--vbase-slate800)]">
            <IconTag className="h-4 w-4" /> Tags
          </h3>
          {company.tag_names && company.tag_names.length ? (
            <div className="flex flex-wrap gap-1.5">
              {company.tag_names.map((t) => (
                <span key={t} className="vbase-chip flex h-7 items-center px-2.5 py-0.5">{t}</span>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[var(--vbase-slate400)]">No tags</p>
          )}
        </div>

        <div className="vbase-card p-4">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-[var(--vbase-slate800)]">
            <IconFileText className="h-4 w-4" /> Notes
          </h3>
          {company.notes ? (
            <p className="whitespace-pre-wrap text-sm text-[var(--vbase-slate700)]">{company.notes}</p>
          ) : (
            <p className="text-sm text-[var(--vbase-slate400)]">No notes</p>
          )}
        </div>
      </div>

      <div className="vbase-card overflow-hidden">
        <div className="flex items-center justify-between border-b border-[var(--vbase-border)] px-4 py-3">
          <h3 className="flex items-center gap-2 font-semibold text-[var(--vbase-slate800)]">
            <IconUsers className="h-4 w-4" /> Contacts at {company.name}
          </h3>
          <span className="text-xs text-[var(--vbase-slate500)]">{contacts.length} contacts</span>
        </div>
        {contacts.length ? (
          <div className="divide-y divide-[var(--vbase-border)]">
            {contacts.map((c) => (
              <div key={c.id} className="flex items-center gap-3 px-4 py-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]">
                  <IconUsers className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-[var(--vbase-slate900)]">{c.display_name || c.full_name}</p>
                  <p className="text-xs text-[var(--vbase-slate500)]">{c.job_title || "No job title"}</p>
                </div>
                {c.email && (
                  <span className="hidden items-center gap-1 text-xs text-[var(--vbase-slate500)] md:flex">
                    <IconMail className="h-3 w-3" />
                    {c.email}
                  </span>
                )}
                <Link to={`/contacts/${c.id}`} className="text-sm text-[var(--vbase-indigo)] hover:underline">Open</Link>
              </div>
            ))}
          </div>
        ) : (
          <p className="px-4 py-8 text-center text-sm text-[var(--vbase-slate500)]">No contacts linked to this company.</p>
        )}
      </div>
    </div>
  );
}
