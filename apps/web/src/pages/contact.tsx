import { useState, useEffect, useCallback } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  IconMail,
  IconMapPin,
  IconBuilding2,
  IconTag,
  IconListChecks,
  IconCopy,
  IconCheck,
  IconExternalLink,
  IconClock,
  IconHistory,
  IconUsers,
  IconHash,
  IconShield,
  IconFileText,
  IconDatabase,
  IconArrowRight,
  IconPencil,
  IconTrash2,
  IconArchive,
  IconSend,
} from "@/lib/icons";
import { api } from "@/lib/api";
import { Contact, Company } from "@/lib/types";
import { ContactAvatar, StageBadge, EmailComposer, SentEmails } from "@/components/crm";
import { ContactSequences } from "@/components/crm/contact-sequences";
import { CRM_STAGES, parsePhone } from "@/lib/crm";
import { toast } from "@/lib/store";
import { ContactEditor } from "@/components/crm/contact-editor";

export function ContactPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [contact, setContact] = useState<Contact | null>(null);
  const [loading, setLoading] = useState(true);
  const [company, setCompany] = useState<{ id: number; name: string } | null>(null);
  const [copied, setCopied] = useState<Record<string, boolean>>({});
  const [tasks, setTasks] = useState<{ id: number; title: string; done: boolean; due_at?: string | null }[]>([]);
  const [newTask, setNewTask] = useState("");
  const [savingStage, setSavingStage] = useState(false);
  const [editing, setEditing] = useState(false);
  const [emailOpen, setEmailOpen] = useState(false);
  // Bumped after a successful send so the history card refetches.
  const [emailVersion, setEmailVersion] = useState(0);

  const loadTasks = async (contactId: string) => {
    try {
      const data = await api.get<{ items: { id: number; title: string; done: boolean; due_at?: string | null }[] }>(
        "/tasks",
        { params: { contact_id: Number(contactId), page_size: 20 } }
      );
      setTasks(data.items);
    } catch {
      /* tasks are secondary — the record still renders */
    }
  };

  useEffect(() => {
    if (!id || isNaN(Number(id))) return;
    let cancelled = false;
    const load = async () => {
      try {
        const c = await api.get<Contact>(`/contacts/${id}`);
        const co = await api.get<Company | null>(`/contacts/${id}/company`).catch(() => null);
        if (!cancelled) {
          setContact(c);
          setCompany(co ? { id: co.id, name: co.name ?? "" } : null);
          loadTasks(id);
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

  const changeStage = async (stage: string) => {
    if (!contact || stage === contact.stage) return;
    setSavingStage(true);
    try {
      const updated = await api.patch<Contact>(`/contacts/${contact.id}`, { stage });
      setContact(updated);
      toast(`Stage set to ${stage}`, "success");
    } catch (e: any) {
      toast(e?.data?.detail || "Could not change stage", "error");
    } finally {
      setSavingStage(false);
    }
  };

  const addTask = async () => {
    if (!contact || !newTask.trim()) {
      toast("Describe the follow-up first", "error");
      return;
    }
    try {
      await api.post("/tasks", { title: newTask.trim(), contact_id: contact.id });
      setNewTask("");
      toast("Follow-up added", "success");
      if (id) loadTasks(id);
    } catch (e: any) {
      toast(e?.data?.detail || "Could not add task", "error");
    }
  };

  const toggleTask = async (task: { id: number; done: boolean }) => {
    try {
      await api.patch(`/tasks/${task.id}`, { done: !task.done });
      if (id) loadTasks(id);
    } catch (e: any) {
      toast(e?.data?.detail || "Could not update task", "error");
    }
  };

  const handleCopy = async (key: string, value: string) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied((prev) => ({ ...prev, [key]: true }));
      toast("Copied", "success");
      setTimeout(() => setCopied((prev) => ({ ...prev, [key]: false })), 1800);
    } catch {
      toast("Copy failed", "error");
    }
  };

  // Declared before the early returns so the hook order never changes
  // between the loading pass and the loaded pass (React rules of hooks).
  const refreshCompany = useCallback(async () => {
    if (!id) {
      setCompany(null);
      return;
    }
    try {
      const linked = await api.get<Company | null>(`/contacts/${id}/company`);
      setCompany(linked ? { id: linked.id, name: linked.name ?? "" } : null);
    } catch {
      setCompany(null);
    }
  }, [id]);

  const refresh = useCallback(
    (u: Contact) => {
      setContact(u);
      void refreshCompany();
    },
    [refreshCompany],
  );

  if (loading && !contact) {
    return (
      <div className="flex items-center gap-3">
        <div className="h-6 w-48 rounded bg-[var(--vbase-slate200)]" />
        <div className="h-6 w-64 rounded bg-[var(--vbase-slate200)]" />
      </div>
    );
  }

  if (!contact) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center text-sm text-[var(--vbase-slate500)]">
        <IconUsers className="h-8 w-8" />
        Contact not found
      </div>
    );
  }

  const name = contact.display_name || contact.full_name || contact.email || "Contact";

  return (
    <div className="flex flex-col gap-6">
      <ContactHeader
        contact={contact}
        name={name}
        stage={contact.stage}
        savingStage={savingStage}
        onStageChange={changeStage}
        onSendEmail={() => setEmailOpen(true)}
      />
      {editing ? (
        <ContactEditor
          contact={contact}
          company={company ? { id: company.id, name: company.name } : null}
          onSaved={refresh}
          onCancel={() => setEditing(false)}
          onDelete={() => {
            toast("Contact deleted", "success");
            navigate("/contacts");
          }}
        />
      ) : (
        <>
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        <DetailSection title="Contact details" icon={<IconMail className="h-4 w-4" />}>
          <div className="space-y-3">
            <Field
              label="Email"
              href={contact.email ? `mailto:${contact.email}` : undefined}
              value={contact.email}
              copyKey="email"
              copyValue={contact.email || ""}
              copied={copied.email}
              onCopy={handleCopy}
            />
            <Field
              label="Phone"
              value={parsePhone(contact.phone)?.display ?? contact.phone}
              copyKey="phone"
              copyValue={contact.phone || ""}
              copied={copied.phone}
              onCopy={handleCopy}
            />
            {contact.phone && !(parsePhone(contact.phone)?.hasCountryCode ?? true) && (
              <p className="rounded-md border border-[var(--vbase-amber)]/30 bg-[var(--vbase-amber)]/5 px-2.5 py-1.5 text-xs text-[var(--vbase-slate600)]">
                No country code on this number — add one (e.g. +91, +1) so it dials from anywhere. Flagged in Data Quality.
              </p>
            )}
            <Field
              label="LinkedIn"
              href={contact.linkedin_url}
              value={contact.linkedin_url}
              copyKey="linkedin"
              copyValue={contact.linkedin_url || ""}
              copied={copied.linkedin}
              onCopy={handleCopy}
            />
          </div>
        </DetailSection>

        <div className="space-y-3">
          <DetailCard title="Location" icon={<IconMapPin className="h-4 w-4" />}>
            {contact.city && <p className="text-sm text-[var(--vbase-slate800)]">{contact.city}</p>}
            {contact.country && <p className="text-xs text-[var(--vbase-slate500)]">{contact.country}</p>}
            {!contact.city && !contact.country && <p className="text-sm text-[var(--vbase-slate400)]">—</p>}
          </DetailCard>

          <DetailCard title="Company" icon={<IconBuilding2 className="h-4 w-4" />}>
            {company ? (
              <Link
                to={`/companies/${company.id}`}
                className="flex items-center gap-2 text-sm font-medium text-[var(--vbase-indigo)] hover:underline"
              >
                <IconBuilding2 className="h-4 w-4" />
                {company.name}
                <IconExternalLink className="h-3.5 w-3.5" />
              </Link>
            ) : contact.company_name ? (
              <span className="text-sm text-[var(--vbase-slate800)]">{contact.company_name}</span>
            ) : (
              <span className="text-sm text-[var(--vbase-slate400)]">—</span>
            )}
          </DetailCard>

          <DetailCard title="Department" icon={<IconHash className="h-4 w-4" />}>
            {contact.department ? <span className="text-sm text-[var(--vbase-slate800)]">{contact.department}</span> : <span className="text-sm text-[var(--vbase-slate400)]">—</span>}
          </DetailCard>

          <DetailCard title="Seniority" icon={<IconShield className="h-4 w-4" />}>
            {contact.seniority ? <span className="text-sm text-[var(--vbase-slate800)]">{contact.seniority}</span> : <span className="text-sm text-[var(--vbase-slate400)]">—</span>}
          </DetailCard>
        </div>

        <div className="space-y-3">
          <DetailCard title="Job title" icon={<IconArrowRight className="h-4 w-4" />}>
            {contact.job_title ? <span className="text-sm text-[var(--vbase-slate800)]">{contact.job_title}</span> : <span className="text-sm text-[var(--vbase-slate400)]">—</span>}
          </DetailCard>

          <DetailCard title="Skills" icon={<IconTag className="h-4 w-4" />}>
            {contact.skills.length ? (
              <div className="flex flex-wrap gap-1.5">
                {contact.skills.map((s) => (
                  <span key={s} className="vbase-chip">
                    {s}
                  </span>
                ))}
              </div>
            ) : (
              <span className="text-sm text-[var(--vbase-slate400)]">—</span>
            )}
          </DetailCard>

          <DetailCard title="Employment history" icon={<IconHistory className="h-4 w-4" />}>
            {contact.employment_history.length ? (
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
              <span className="text-sm text-[var(--vbase-slate400)]">—</span>
            )}
          </DetailCard>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <DetailCard title="Tags" icon={<IconTag className="h-4 w-4" />}>
          {contact.tag_names && contact.tag_names.length ? (
            <div className="flex flex-wrap gap-1.5">
              {contact.tag_names.map((t) => (
                <span key={t} className="vbase-chip">
                  {t}
                </span>
              ))}
            </div>
          ) : (
            <span className="text-sm text-[var(--vbase-slate400)]">No tags</span>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              onClick={() => setEditing(true)}
              className="vbase-btn-primary flex items-center gap-1.5 text-sm"
            >
              <IconPencil className="h-4 w-4" />
              Edit record
            </button>
            <Link
              to={`/contacts/${contact.id}/edit`}
              className="vbase-btn-secondary flex items-center gap-1.5 text-sm"
            >
              <IconExternalLink className="h-4 w-4" />
              Open full editor
            </Link>
            <button
              onClick={() => {
                if (contact.is_archived) {
                  api.post<Contact>(`/contacts/${contact.id}/restore`).then((u) => {
                    setContact(u);
                    toast(`Contact restored`, "success");
                  });
                } else {
                  api.post<Contact>(`/contacts/${contact.id}/archive`).then((u) => {
                    setContact(u);
                    toast(`Contact archived`, "success");
                  });
                }
              }}
              className="vbase-btn-ghost flex items-center gap-1.5 text-sm text-[var(--vbase-amber)]"
            >
              <IconArchive className="h-4 w-4" />
              {contact.is_archived ? "Restore" : "Archive"}
            </button>
            <button
              onClick={() => {
                if (!window.confirm(`Delete this contact? This cannot be undone.`)) return;
                api.delete(`/contacts/${contact.id}`).then(() => {
                  toast(`Contact deleted`, "success");
                  navigate("/contacts");
                });
              }}
              className="vbase-btn-danger flex items-center gap-1.5 text-sm"
            >
              <IconTrash2 className="h-4 w-4" />
              Delete
            </button>
          </div>
        </DetailCard>

        <DetailCard title="Lists" icon={<IconListChecks className="h-4 w-4" />}>
          <p className="text-sm text-[var(--vbase-slate400)]">List membership shown in Lists view.</p>
        </DetailCard>

        <DetailCard title="Source" icon={<IconDatabase className="h-4 w-4" />}>
          <span className="text-sm text-[var(--vbase-slate800)]">{contact.source || "Manual"}</span>
        </DetailCard>

        <DetailCard title="Last verified" icon={<IconClock className="h-4 w-4" />}>
          {contact.last_verified ? (
            <span className="text-sm text-[var(--vbase-slate800)]">{new Date(contact.last_verified).toLocaleString()}</span>
          ) : (
            <span className="text-sm text-[var(--vbase-slate400)]">Never</span>
          )}
        </DetailCard>

        <div className="md:col-span-2">
          <DetailCard title="Emails" icon={<IconMail className="h-4 w-4" />}>
            <SentEmails key={emailVersion} contactId={contact.id} />
          </DetailCard>
        </div>

        <div className="md:col-span-2">
          <ContactSequences contactId={contact.id} />
        </div>

        <div className="md:col-span-2">
          <DetailCard title={`Follow-ups (${tasks.filter((t) => !t.done).length} open)`} icon={<IconListChecks className="h-4 w-4" />}>
            {tasks.length ? (
              <ul className="space-y-1.5">
                {tasks.map((t) => (
                  <li key={t.id} className="flex items-center gap-2 text-sm">
                    <button
                      type="button"
                      onClick={() => toggleTask(t)}
                      aria-label={t.done ? `Reopen ${t.title}` : `Complete ${t.title}`}
                      className={`flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full border-2 transition-colors ${
                        t.done
                          ? "border-[var(--vbase-green)] bg-[var(--vbase-green)] text-white"
                          : "border-[var(--vbase-border)] bg-[var(--vbase-bg)] text-[var(--vbase-slate600)] hover:border-[var(--vbase-indigo)] hover:text-[var(--vbase-indigo)]"
                      }`}
                    >
                      <IconCheck className="h-2.5 w-2.5" />
                    </button>
                    <span className={`min-w-0 flex-1 truncate ${t.done ? "text-[var(--vbase-slate400)] line-through" : "text-[var(--vbase-slate800)]"}`} title={t.title}>
                      {t.title}
                    </span>
                    {t.due_at && <span className="flex-shrink-0 text-xs text-[var(--vbase-slate500)]">{new Date(t.due_at).toLocaleDateString()}</span>}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-[var(--vbase-slate400)]">No follow-ups yet.</p>
            )}
            <div className="mt-2.5 flex gap-2">
              <input
                value={newTask}
                onChange={(e) => setNewTask(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") addTask(); }}
                placeholder="Call back next week…"
                className="vbase-input h-8 text-sm"
              />
              <button onClick={addTask} className="vbase-btn-secondary flex-shrink-0 px-2.5 text-sm">Add</button>
            </div>
          </DetailCard>
        </div>

        <div className="md:col-span-2">
          <DetailCard title="Notes" icon={<IconFileText className="h-4 w-4" />}>
            {contact.notes ? (
              <p className="text-sm text-[var(--vbase-slate700)] whitespace-pre-wrap">{contact.notes}</p>
            ) : (
              <span className="text-sm text-[var(--vbase-slate400)]">No notes</span>
            )}
          </DetailCard>
        </div>
      </div>

        </>
      )}

      <EmailComposer
        open={emailOpen}
        to={contact.email}
        name={name}
        contactId={contact.id}
        onClose={() => setEmailOpen(false)}
        onSent={() => setEmailVersion((v) => v + 1)}
      />
    </div>
  );
}

function ContactHeader({ contact, name, stage, savingStage, onStageChange, onSendEmail }: { contact: Contact; name: string; stage?: string | null; savingStage: boolean; onStageChange: (stage: string) => void; onSendEmail: () => void }) {
  const [editingHeader, setEditingHeader] = useState(false);
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex min-w-0 items-start gap-4">
        <ContactAvatar name={name} size={56} />
        <div className="min-w-0">
          {editingHeader ? (
            <input
              type="text"
              defaultValue={name}
              onBlur={(e) => {
                if (contact && e.target.value.trim() && e.target.value.trim() !== contact.display_name && e.target.value.trim() !== (contact.full_name || "")) {
                  api.patch(`/contacts/${contact.id}`, { full_name: e.target.value.trim() }).then(() => toast(`Name updated`, "success"));
                }
                setEditingHeader(false);
              }}
              onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
              className="vbase-input h-8 w-64 text-2xl font-semibold text-[var(--vbase-slate900)]"
              autoFocus
            />
          ) : (
            <h1 className="truncate text-2xl font-semibold text-[var(--vbase-slate900)]" title={name}>{name}</h1>
          )}
          <p className="mt-1 truncate text-sm text-[var(--vbase-slate500)]">{contact.job_title || "No job title"}</p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {editingHeader ? (
          <>
            <button onClick={() => setEditingHeader(false)} className="vbase-btn-ghost flex items-center gap-1.5 text-sm">Cancel</button>
            <button onClick={() => setEditingHeader(false)} className="vbase-btn-secondary flex items-center gap-1.5 text-sm">Done</button>
          </>
        ) : (
          <>
            <button
              onClick={onSendEmail}
              disabled={!contact.email}
              title={contact.email ? `Email ${contact.email}` : "This contact has no email address"}
              className="vbase-btn-primary flex items-center gap-1.5 text-sm"
            >
              <IconSend className="h-4 w-4" />
              Send email
            </button>
            <button onClick={() => setEditingHeader(true)} className="vbase-btn-ghost flex items-center gap-1.5 text-sm">
              <IconPencil className="h-4 w-4" />
              Rename
            </button>
          </>
        )}
        <StageBadge stage={stage} />
        <select
          value={stage || "New"}
          disabled={savingStage}
          onChange={(e) => onStageChange(e.target.value)}
          aria-label="Pipeline stage"
          className="vbase-select h-8 text-sm"
        >
          {CRM_STAGES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <QualityChip score={contact.data_quality_score} />
      </div>
    </div>
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

function DetailSection({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="vbase-card p-4">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-[var(--vbase-slate800)]">
        {icon}
        {title}
      </h3>
      {children}
    </div>
  );
}

function DetailCard({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] p-4">
      <div className="mt-0.5 flex h-7 w-7 items-center justify-center rounded border border-[var(--vbase-border)] bg-[var(--vbase-bg)] text-[var(--vbase-slate500)]">
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-[var(--vbase-slate500)]">{title}</p>
        <div className="mt-1.5">{children}</div>
      </div>
    </div>
  );
}

function Field({ label, href, value, copyKey, copyValue, copied, onCopy }: {
  label: string;
  href?: string | null;
  value?: string | null | undefined;
  copyKey: string;
  copyValue: string;
  copied?: boolean;
  onCopy?: (key: string, value: string) => void;
}) {
  const external = href && /^https?:/i.test(href);
  return (
    <div className="flex items-start justify-between gap-2">
      <div className="min-w-0">
        <p className="text-xs text-[var(--vbase-slate500)]">{label}</p>
        <p className={`mt-0.5 truncate text-sm ${href ? "text-[var(--vbase-indigo)] hover:underline" : "text-[var(--vbase-slate800)]"}`}>
          {href ? (
            <a href={href} {...external ? { target: "_blank", rel: "noreferrer" } : {}} className="hover:underline">
              {value || href.replace(/^mailto:/, "")}
            </a>
          ) : (
            value || "—"
          )}
        </p>
      </div>
      <button
        type="button"
        onClick={() => {
          onCopy?.(copyKey, copyValue);
        }}
        aria-label={`Copy ${label}`}
        title={copied ? "Copied" : `Copy ${label}`}
        className={`vbase-btn vbase-btn-icon-sm vbase-btn-ghost ${
          copied ? "text-[var(--vbase-green)]" : ""
        }`}
      >
        {copied ? <IconCheck className="h-4 w-4" /> : <IconCopy className="h-4 w-4" />}
      </button>
    </div>
  );
}
