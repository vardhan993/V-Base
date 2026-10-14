import { useState, useCallback, useMemo } from "react";
import { api } from "@/lib/api";
import { Lead, ScoreRule } from "@/lib/types";
import { toast } from "@/lib/store";
import { IconX, IconTarget, IconFlame, IconArrowRightLeft } from "@/lib/icons";

export const LEAD_STAGES = ["New", "Working", "Qualified", "Unqualified", "Nurture", "Converted"] as const;
export const LEAD_STATUSES = [
  "New",
  "Open",
  "Working",
  "Contacted",
  "Nurture",
  "Disqualified",
] as const;
export const LEAD_PRIORITIES = ["Low", "Medium", "High", "Urgent"] as const;

/** Editable text form of a lead. Values stay strings so one input binding
 * covers every column, and empty strings normalize to null on the way out. */
interface LeadDraft {
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
  linkedin_url: string;
  website: string;
  company_name: string;
  company_domain: string;
  industry: string;
  employee_count: string;
  company_size: string;
  city: string;
  state: string;
  country: string;
  lead_source: string;
  campaign: string;
  lifecycle_stage: string;
  lead_status: string;
  priority: string;
  next_follow_up_at: string;
  consent_status: string;
  disqualified_reason: string;
  notes: string;
  tags: string;
}

const EMPTY_DRAFT: LeadDraft = {
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
  linkedin_url: "",
  website: "",
  company_name: "",
  company_domain: "",
  industry: "",
  employee_count: "",
  company_size: "",
  city: "",
  state: "",
  country: "",
  lead_source: "",
  campaign: "",
  lifecycle_stage: "New",
  lead_status: "New",
  priority: "Medium",
  next_follow_up_at: "",
  consent_status: "",
  disqualified_reason: "",
  notes: "",
  tags: "",
};

type StringField = keyof LeadDraft;

const EMAIL_STATUS_OPTIONS = ["", "Verified", "Pending", "Invalid", "Missing"];
const PHONE_STATUS_OPTIONS = ["", "Verified", "Pending", "Invalid", "Missing"];
export const CONSENT_OPTIONS = ["", "Opted in", "Not asked", "Opted out"];
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

function leadToDraft(lead: Lead | null): LeadDraft {
  if (!lead) return { ...EMPTY_DRAFT };
  return {
    first_name: lead.first_name ?? "",
    last_name: lead.last_name ?? "",
    full_name: lead.full_name ?? "",
    job_title: lead.job_title ?? "",
    department: lead.department ?? "",
    seniority: lead.seniority ?? "",
    email: lead.email ?? "",
    email_status: lead.email_status ?? "",
    phone: lead.phone ?? "",
    phone_status: lead.phone_status ?? "",
    linkedin_url: lead.linkedin_url ?? "",
    website: lead.website ?? "",
    company_name: lead.company_name ?? "",
    company_domain: lead.company_domain ?? "",
    industry: lead.industry ?? "",
    employee_count: lead.employee_count != null ? String(lead.employee_count) : "",
    company_size: lead.company_size ?? "",
    city: lead.city ?? "",
    state: lead.state ?? "",
    country: lead.country ?? "",
    lead_source: lead.lead_source ?? "",
    campaign: lead.campaign ?? "",
    lifecycle_stage: lead.lifecycle_stage || "New",
    lead_status: lead.lead_status || "New",
    priority: lead.priority || "Medium",
    next_follow_up_at: localDateTime(lead.next_follow_up_at),
    consent_status: lead.consent_status ?? "",
    disqualified_reason: lead.disqualified_reason ?? "",
    notes: lead.notes ?? "",
    tags: (lead.tag_names || []).join(", "),
  };
}

function draftToApi(draft: LeadDraft): Record<string, unknown> {
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
    linkedin_url: text(draft.linkedin_url),
    website: text(draft.website),
    company_name: text(draft.company_name),
    company_domain: text(draft.company_domain),
    industry: text(draft.industry),
    employee_count: integer(draft.employee_count),
    company_size: text(draft.company_size),
    city: text(draft.city),
    state: text(draft.state),
    country: text(draft.country),
    lead_source: text(draft.lead_source),
    campaign: text(draft.campaign),
    lifecycle_stage: draft.lifecycle_stage || "New",
    lead_status: draft.lead_status || "New",
    priority: draft.priority || "Medium",
    next_follow_up_at: draft.next_follow_up_at ? new Date(draft.next_follow_up_at).toISOString() : null,
    consent_status: text(draft.consent_status),
    disqualified_reason: text(draft.disqualified_reason),
    notes: text(draft.notes),
  };
}

function changedKeys(before: Record<string, unknown>, after: Record<string, unknown>): string[] {
  return Object.keys(after).filter(
    (key) => JSON.stringify(before[key]) !== JSON.stringify(after[key]),
  );
}

export interface LeadEditorProps {
  /** Pass a lead to edit it; omit or pass null to create a new one. */
  lead?: Lead | null;
  onSaved: (lead: Lead) => void;
  onDelete?: (lead: Lead) => void;
  onConvert?: (lead: Lead) => void;
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

/** The score, its split, and which rules fired. Nothing here is inferred —
 * every line comes from the rules the server actually applied. */
export function ScorePanel({ lead }: { lead: Lead }) {
  const rules: ScoreRule[] = lead.score_breakdown || [];
  const fit = rules.filter((r) => r.kind === "fit");
  const engagement = rules.filter((r) => r.kind === "engagement");
  return (
    <div className="vbase-card p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-[var(--vbase-slate800)]">
          <IconTarget className="h-4 w-4" />
          Lead score
        </h3>
        <span className="text-2xl font-semibold text-[var(--vbase-slate900)]">{lead.lead_score}<span className="text-sm text-[var(--vbase-slate400)]">/100</span></span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-3 text-xs">
        <div className="rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-2.5 py-2">
          <p className="text-[var(--vbase-slate500)]">Fit</p>
          <p className="text-base font-semibold text-[var(--vbase-slate800)]">{lead.fit_score}</p>
        </div>
        <div className="rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-2.5 py-2">
          <p className="text-[var(--vbase-slate500)]">Engagement</p>
          <p className="text-base font-semibold text-[var(--vbase-slate800)]">{lead.engagement_score}</p>
        </div>
      </div>
      {lead.score_summary && (
        <p className="mt-2 text-xs text-[var(--vbase-slate500)]">{lead.score_summary}</p>
      )}
      {lead.score_updated_at && (
        <p className="mt-1 text-[11px] text-[var(--vbase-slate400)]">
          Last calculated {new Date(lead.score_updated_at).toLocaleString()}
        </p>
      )}

      <details className="mt-3">
        <summary className="cursor-pointer text-xs font-medium text-[var(--vbase-indigo)]">
          Why this score ({rules.filter((r) => r.earned).length} of {rules.length} rules met)
        </summary>
        <div className="mt-2 space-y-2">
          {[
            { title: "Fit signals", items: fit, icon: <IconTarget className="h-3.5 w-3.5" /> },
            {
              title: "Engagement (logged activity only)",
              items: engagement,
              icon: <IconFlame className="h-3.5 w-3.5" />,
            },
          ].map((group) => (
            <div key={group.title}>
              <p className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-[var(--vbase-slate500)]">
                {group.icon}
                {group.title}
              </p>
              <ul className="space-y-1">
                {group.items.map((rule) => (
                  <li key={rule.key} className="flex items-start gap-2 text-xs">
                    <span
                      className={`mt-0.5 inline-block h-3.5 w-3.5 flex-shrink-0 rounded-full border ${
                        rule.earned
                          ? "border-[var(--vbase-green)] bg-[var(--vbase-green)]/20"
                          : "border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)]"
                      }`}
                      title={rule.earned ? "Rule met" : "Rule not met"}
                    />
                    <span className="min-w-0 flex-1">
                      <span className={rule.earned ? "text-[var(--vbase-slate800)]" : "text-[var(--vbase-slate500)]"}>
                        {rule.label}
                      </span>
                      <span className="ml-1 text-[var(--vbase-slate400)]">
                        {rule.earned ? `+${rule.points}` : `0/${rule.weight}`}
                      </span>
                      <span className="block text-[11px] text-[var(--vbase-slate400)]">{rule.detail}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}

export function LeadEditor({ lead, onSaved, onDelete, onConvert, onCancel }: LeadEditorProps) {
  const isCreate = !lead;
  const original = useMemo(() => leadToDraft(lead ?? null), [lead]);
  const [draft, setDraft] = useState<LeadDraft>(() => leadToDraft(lead ?? null));
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [archived, setArchived] = useState(lead?.is_archived ?? false);
  const [invalid, setInvalid] = useState<string | null>(null);
  const [saved, setSaved] = useState<Lead | null>(lead ?? null);

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
    const hasIdentity =
      draft.first_name.trim() ||
      draft.last_name.trim() ||
      draft.full_name.trim() ||
      draft.email.trim() ||
      draft.company_name.trim();
    if (!hasIdentity) {
      setInvalid("Add at least a name, an email address or a company before saving.");
      return;
    }
    if (!isCreate && !changed.length && !changedTags) {
      toast("No changes", "info");
      return;
    }

    setSaving(true);
    try {
      let result: Lead;
      if (isCreate) {
        result = await api.post<Lead>("/leads", {
          ...nextBody,
          ...(draft.tags.trim() ? { tags: splitList(draft.tags) } : {}),
        });
        toast("Lead created", "success");
      } else {
        const body: Record<string, unknown> = {};
        for (const key of changed) body[key] = nextBody[key];
        if (changedTags) body.tags = splitList(draft.tags);
        result = await api.patch<Lead>(`/leads/${lead!.id}`, body);
        toast("Lead updated", "success");
      }
      setDraft(leadToDraft(result));
      setSaved(result);
      setArchived(result.is_archived);
      onSaved(result);
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
    setDraft(leadToDraft(lead ?? null));
    setInvalid(null);
  };

  const setArchivedFlag = async (next: boolean) => {
    if (!lead) return;
    setSaving(true);
    try {
      const updated = await api.post<Lead>(`/leads/${lead.id}/${next ? "archive" : "restore"}`);
      setArchived(updated.is_archived);
      setDraft(leadToDraft(updated));
      setSaved(updated);
      onSaved(updated);
      toast(next ? "Lead archived" : "Lead restored", "success");
    } catch (e: any) {
      toast(e?.data?.detail || "Could not update archive state", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!lead) return;
    if (!window.confirm("Delete this lead? This cannot be undone.")) return;
    setDeleting(true);
    try {
      await api.delete(`/leads/${lead.id}`);
      toast("Lead deleted", "success");
      onDelete?.(lead);
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
            ? "Capture what you know now — the score updates as the record fills in."
            : "Edit any single field and save. Use the × beside a label to clear just that field."}
        </p>
        {!isCreate && (changed.length > 0 || changedTags) && (
          <span className="text-xs text-[var(--vbase-indigo)]">
            {changed.length + (changedTags ? 1 : 0)} field(s) changed
          </span>
        )}
      </div>

      {saved && !isCreate && <ScorePanel lead={saved} />}

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
          note="Used for the display name when set."
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
        <FieldRow
          label="Seniority"
          value={draft.seniority}
          onClear={() => setValue("seniority", "")}
          note="Feeds the decision-maker rule."
        >
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
        <FieldRow
          label="Business email"
          value={draft.email}
          onClear={() => setValue("email", "")}
          note="A work-domain address scores higher than a free provider."
        >
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
        <FieldRow label="Phone" value={draft.phone} onClear={() => setValue("phone", "")}>
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
        <FieldRow label="LinkedIn profile" value={draft.linkedin_url} onClear={() => setValue("linkedin_url", "")}>
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
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <FieldRow
          label="Company"
          value={draft.company_name}
          onClear={() => setValue("company_name", "")}
          note="Matching an existing company links the lead."
        >
          <input
            type="text"
            name="company_name"
            value={draft.company_name}
            onChange={(e) => setValue("company_name", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
            autoComplete="off"
          />
        </FieldRow>
        <FieldRow label="Company domain" value={draft.company_domain} onClear={() => setValue("company_domain", "")}>
          <input
            type="text"
            name="company_domain"
            value={draft.company_domain}
            onChange={(e) => setValue("company_domain", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
            autoComplete="off"
          />
        </FieldRow>
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
        <FieldRow
          label="Employees"
          value={draft.employee_count}
          onClear={() => setValue("employee_count", "")}
          note="Feeds the target headcount band rule."
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

      <div className="grid gap-4 md:grid-cols-4">
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
        <FieldRow label="Lead source" value={draft.lead_source} onClear={() => setValue("lead_source", "")}>
          <input
            type="text"
            name="lead_source"
            value={draft.lead_source}
            onChange={(e) => setValue("lead_source", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
        <FieldRow label="Campaign" value={draft.campaign} onClear={() => setValue("campaign", "")}>
          <input
            type="text"
            name="campaign"
            value={draft.campaign}
            onChange={(e) => setValue("campaign", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <FieldRow label="Lifecycle stage" value={draft.lifecycle_stage} onClear={() => setValue("lifecycle_stage", "New")}>
          <select
            name="lifecycle_stage"
            value={draft.lifecycle_stage}
            onChange={(e) => setValue("lifecycle_stage", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy || draft.lead_status === "Converted"}
          >
            {LEAD_STAGES.map((stage) => (
              <option key={stage} value={stage}>
                {stage}
              </option>
            ))}
          </select>
        </FieldRow>
        <FieldRow
          label="Lead status"
          value={draft.lead_status}
          onClear={() => setValue("lead_status", "New")}
          note="Converted is set by the convert action."
        >
          <select
            name="lead_status"
            value={draft.lead_status}
            onChange={(e) => setValue("lead_status", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          >
            {LEAD_STATUSES.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
            {draft.lead_status === "Converted" && <option value="Converted">Converted</option>}
          </select>
        </FieldRow>
        <FieldRow label="Priority" value={draft.priority} onClear={() => setValue("priority", "Medium")}>
          <select
            name="priority"
            value={draft.priority}
            onChange={(e) => setValue("priority", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          >
            {LEAD_PRIORITIES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </FieldRow>
        <FieldRow
          label="Next follow-up"
          value={draft.next_follow_up_at}
          onClear={() => setValue("next_follow_up_at", "")}
          note="Drives the overdue indicator."
        >
          <input
            type="datetime-local"
            name="next_follow_up_at"
            value={draft.next_follow_up_at}
            onChange={(e) => setValue("next_follow_up_at", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          />
        </FieldRow>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <FieldRow
          label="Communication preference"
          value={draft.consent_status}
          onClear={() => setValue("consent_status", "")}
        >
          <select
            name="consent_status"
            value={draft.consent_status}
            onChange={(e) => setValue("consent_status", e.target.value)}
            className="vbase-input h-9 w-full"
            disabled={busy}
          >
            {CONSENT_OPTIONS.map((value) => (
              <option key={value || "unset"} value={value}>
                {value || "Not recorded"}
              </option>
            ))}
          </select>
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
          label="Disqualification reason"
          value={draft.disqualified_reason}
          onClear={() => setValue("disqualified_reason", "")}
          note="Recorded when a lead is disqualified, never guessed."
        >
          <input
            type="text"
            name="disqualified_reason"
            value={draft.disqualified_reason}
            onChange={(e) => setValue("disqualified_reason", e.target.value)}
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
          {saving ? "Saving…" : isCreate ? "Create lead" : "Save changes"}
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
        {!isCreate && onConvert && !lead?.converted_at && (
          <button
            onClick={() => onConvert(lead!)}
            className="vbase-btn-secondary flex items-center gap-1.5 text-sm"
            disabled={busy}
          >
            <IconArrowRightLeft className="h-4 w-4" />
            Convert to contact
          </button>
        )}
        <span className="text-xs text-[var(--vbase-slate500)]">
          {isCreate
            ? "Scoring and the activity log both start from this record."
            : changed.length || changedTags
              ? "Only the fields you changed are sent; scoring re-runs for scored fields."
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
            Delete lead
          </button>
        </div>
      )}
    </div>
  );
}
