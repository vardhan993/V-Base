import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { IconMail, IconMapPin, IconBuilding2, IconTag, IconListChecks, IconCopy, IconCheck, IconExternalLink, IconClock, IconHistory, IconUsers, IconHash, IconShield, IconFileText, IconDatabase } from "@/lib/icons";
import { api } from "@/lib/api";
import { Contact, Company } from "@/lib/types";
import { toast } from "@/lib/store";

function DetailSection({ title, icon, children }: any) {
  return (
    <div className="vbase-card p-4">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-[var(--vbase-slate800)]">{icon} {title}</h3>
      {children}
    </div>
  );
}

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

function QualityBadge({ score, className }: any) {
  return <div className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${className}`}>{score} / 100</div>;
}

export function ContactPage() {
  const { id } = useParams<{ id: string }>();
  const [contact, setContact] = useState<Contact | null>(null);
  const [loading, setLoading] = useState(true);
  const [company, setCompany] = useState<Company | null>(null);
  const [copied, setCopied] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!id || isNaN(Number(id))) return;
    let cancelled = false;
    const load = async () => {
      try {
        const c = await api.get<Contact>(`/contacts/${id}`);
        const co = await api.get<Company | null>(`/contacts/${id}/company`).catch(() => null);
        if (!cancelled) {
          setContact(c);
          setCompany(co);
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

  const handleCopy = async (key: string, value: string) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied((prev) => ({ ...prev, [key]: true }));
      toast("Copied", "success");
      setTimeout(() => setCopied((prev) => ({ ...prev, [key]: false })), 1800);
    } catch { toast("Copy failed", "error"); }
  };

  const qualityClass = contact ? (contact.data_quality_score >= 70 ? "bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]" : contact.data_quality_score >= 40 ? "bg-[var(--vbase-amber)]/10 text-[var(--vbase-amber)]" : "bg-[var(--vbase-red)]/10 text-[var(--vbase-red)]") : "bg-[var(--vbase-slate100)] text-[var(--vbase-slate500)]";

  return (
    <div className="flex flex-col gap-6">
      {loading && !contact ? (
        <div className="flex items-center gap-3"><div className="h-6 w-48 rounded bg-[var(--vbase-slate200)]" /><div className="h-6 w-64 rounded bg-[var(--vbase-slate200)]" /></div>
      ) : !contact ? (
        <div className="flex flex-col items-center gap-3 py-16 text-center text-sm text-[var(--vbase-slate500)]">
          <IconUsers className="h-8 w-8" />
          Contact not found
        </div>
      ) : (
        <>
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-4">
              <div className="mt-1 flex h-14 w-14 items-center justify-center rounded-full bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]">
                <IconUsers className="h-7 w-7" />
              </div>
              <div>
                <h1 className="text-2xl font-semibold text-[var(--vbase-slate900)]">{contact.display_name || contact.full_name || "Contact"}</h1>
                <p className="mt-1 text-sm text-[var(--vbase-slate500)]">{contact.job_title || "No job title"}</p>
              </div>
            </div>
            <QualityBadge score={contact.data_quality_score} className={qualityClass} />
          </div>

          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            <DetailSection title="Contact details" icon={<IconMail className="h-4 w-4" />}>
              <div className="space-y-3">
                <Field label="Email" href={contact.email ? `mailto:${contact.email}` : undefined} value={contact.email} copyKey="email" copyValue={contact.email || ""} copied={copied.email} onCopy={handleCopy} />
                <Field label="Phone" value={contact.phone} copyKey="phone" copyValue={contact.phone || ""} copied={copied.phone} onCopy={handleCopy} />
                <Field label="LinkedIn" href={contact.linkedin_url} value={contact.linkedin_url} copyKey="linkedin" copyValue={contact.linkedin_url || ""} copied={copied.linkedin} onCopy={handleCopy} />
              </div>
            </DetailSection>

            <div className="space-y-3">
              <DetailCard title="Location" icon={<IconMapPin className="h-4 w-4" />}>
                {contact.city && <p className="text-sm text-[var(--vbase-slate800)]">{contact.city}</p>}
                {contact.country && <p className="text-xs text-[var(--vbase-slate500)]">{contact.country}</p>}
                {(!contact.city && !contact.country) && <p className="text-sm text-[var(--vbase-slate400)]">—</p>}
              </DetailCard>

              <DetailCard title="Company" icon={<IconBuilding2 className="h-4 w-4" />}>
                {company ? (
                  <Link to={`/companies/${company.id}`} className="flex items-center gap-2 text-sm font-medium text-[var(--vbase-indigo)] hover:underline">
                    <IconBuilding2 className="h-4 w-4" />
                    {company.name}
                    <IconExternalLink className="h-3 w-3" />
                  </Link>
                ) : contact.company_name ? (
                  <p className="text-sm text-[var(--vbase-slate800)]">{contact.company_name}</p>
                ) : (
                  <p className="text-sm text-[var(--vbase-slate400)]">—</p>
                )}
              </DetailCard>

              <DetailCard title="Department" icon={<IconHash className="h-4 w-4" />}>
                {contact.department || <p className="text-sm text-[var(--vbase-slate400)]">—</p>}
              </DetailCard>

              <DetailCard title="Seniority" icon={<IconShield className="h-4 w-4" />}>
                {contact.seniority || <p className="text-sm text-[var(--vbase-slate400)]">—</p>}
              </DetailCard>
            </div>

            <div className="space-y-3">
              <DetailCard title="Skills" icon={<IconTag className="h-4 w-4" />}>
                {contact.skills && contact.skills.length ? (
                  <div className="flex flex-wrap gap-1.5">
                    {contact.skills.map((s) => (
                      <span key={s} className="vbase-chip flex h-7 items-center px-2.5 py-0.5">{s}</span>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-[var(--vbase-slate400)]">—</p>
                )}
              </DetailCard>

              <DetailCard title="Employment history" icon={<IconHistory className="h-4 w-4" />}>
                {contact.employment_history && contact.employment_history.length ? (
                  <ul className="mt-2 space-y-2">
                    {contact.employment_history.map((e: any, i: number) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-[var(--vbase-slate600)]">
                        {e.company_name && <span className="font-medium text-[var(--vbase-slate800)]">{e.company_name}</span>}
                        {e.job_title && <span> · {e.job_title}</span>}
                        {e.start_date && <span> · {e.start_date}</span>}
                        {e.end_date && <span className="text-[var(--vbase-slate400)]"> — {e.end_date}</span>}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-[var(--vbase-slate400)]">—</p>
                )}
              </DetailCard>
            </div>
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            <DetailCard title="Tags" icon={<IconTag className="h-4 w-4" />}>
              {contact.tag_names && contact.tag_names.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {contact.tag_names.map((t) => (
                    <span key={t} className="vbase-chip flex h-7 items-center px-2.5 py-0.5">{t}</span>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-[var(--vbase-slate400)]">No tags</p>
              )}
            </DetailCard>

            <DetailCard title="Lists" icon={<IconListChecks className="h-4 w-4" />}>
              <p className="text-sm text-[var(--vbase-slate400)]">List membership shown in Lists view.</p>
            </DetailCard>

            <DetailCard title="Source" icon={<IconDatabase className="h-4 w-4" />}>
              <p className="text-sm text-[var(--vbase-slate800)]">{contact.source || "Manual"}</p>
            </DetailCard>

            <DetailCard title="Last verified" icon={<IconClock className="h-4 w-4" />}>
              {contact.last_verified ? new Date(contact.last_verified).toLocaleString() : <p className="text-sm text-[var(--vbase-slate400)]">Never</p>}
            </DetailCard>

            <div className="md:col-span-2">
              <DetailCard title="Notes" icon={<IconFileText className="h-4 w-4" />}>
                {contact.notes ? (
                  <p className="text-sm text-[var(--vbase-slate700)] whitespace-pre-wrap">{contact.notes}</p>
                ) : (
                  <p className="text-sm text-[var(--vbase-slate400)]">No notes</p>
                )}
              </DetailCard>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Field({ label, href, value, copyKey, copyValue, copied, onCopy }: any) {
  const copiedVisible = copied;
  const external = href && /^https?:/i.test(href);
  return (
    <div className="flex items-start justify-between gap-2">
      <div className="min-w-0">
        <p className="text-xs text-[var(--vbase-slate500)]">{label}</p>
        <p className={`mt-0.5 truncate text-sm ${href ? "text-[var(--vbase-indigo)] hover:underline" : "text-[var(--vbase-slate800)]"}`}>
          {href ? (
            <a href={href} {...(external ? { target: "_blank", rel: "noreferrer" } : {})} className="hover:underline">{value || href.replace(/^mailto:/, "")}</a>
          ) : (
            value || "—"
          )}
        </p>
      </div>
      <button onClick={() => { onCopy?.(copyKey, copyValue); }} className="flex h-7 items-center justify-center rounded text-[var(--vbase-slate400)] hover:bg-[var(--vbase-bg-alt)] hover:text-[var(--vbase-slate700)]">
        {copiedVisible ? <IconCheck className="h-4 w-4 text-[var(--vbase-green)]" /> : <IconCopy className="h-4 w-4" />}
      </button>
    </div>
  );
}
