import { useState, useEffect, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  IconPlus,
  IconSearch,
  IconDownload,
  IconX,
  IconSparkle,
  IconArchive,
  IconTrash2,
  IconArrowRightLeft,
  IconTarget,
} from "@/lib/icons";
import { api } from "@/lib/api";
import { Lead } from "@/lib/types";
import { downloadCsv } from "@/lib/download";
import { EntityActions, EmptyState } from "@/components/crm";
import { LEAD_STAGES, LEAD_PRIORITIES } from "@/components/crm";
import { toast } from "@/lib/store";

interface LeadFilters {
  lifecycle_stage?: string;
  lead_status?: string;
  priority?: string;
  country?: string;
  industry?: string;
  overdue_follow_up?: boolean;
  converted?: boolean;
}

export function LeadsPage() {
  const navigate = useNavigate();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<LeadFilters>({});
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [converting, setConverting] = useState<number | null>(null);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number | boolean | undefined> = {
        page,
        page_size: pageSize,
        sort: "updated_at",
        order: "desc",
      };
      if (search) params.q = search;
      if (filters.lifecycle_stage) params.lifecycle_stage = filters.lifecycle_stage;
      if (filters.lead_status) params.lead_status = filters.lead_status;
      if (filters.priority) params.priority = filters.priority;
      if (filters.country) params.country = filters.country;
      if (filters.industry) params.industry = filters.industry;
      if (filters.overdue_follow_up) params.overdue_follow_up = true;
      if (filters.converted !== undefined) params.converted = filters.converted;

      const data = await api.get<{ items: Lead[]; total: number }>("/leads", { params });
      setLeads(data.items);
      setTotal(data.total);
    } catch (e: any) {
      toast(e?.data?.detail || "Could not load leads", "error");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, filters]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  useEffect(() => {
    setSelected(new Set());
  }, [page, search, filters]);

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelected((prev) =>
      prev.size === leads.length && leads.length > 0 ? new Set() : new Set(leads.map((l) => l.id)),
    );
  };

  const runBulk = async (action: "archive" | "delete") => {
    if (selected.size === 0 || bulkBusy) return;
    if (
      action === "delete" &&
      !window.confirm(
        `Delete ${selected.size} lead(s)? Converted history on the linked contacts is kept. This cannot be undone.`,
      )
    ) {
      return;
    }
    setBulkBusy(true);
    const ids = [...selected];
    let ok = 0;
    let failed = 0;
    for (const id of ids) {
      try {
        if (action === "archive") await api.post(`/leads/${id}/archive`);
        else await api.delete(`/leads/${id}`);
        ok += 1;
      } catch {
        failed += 1;
      }
    }
    setSelected(new Set());
    setBulkBusy(false);
    if (failed) toast(`${ok} ${action}d, ${failed} failed`, "error");
    else toast(`${ok} lead(s) ${action}d`, "success");
    fetchList();
  };

  const quickConvert = async (lead: Lead) => {
    if (lead.converted_at) {
      toast("This lead is already converted", "info");
      return;
    }
    if (!window.confirm(`Convert ${lead.display_name || lead.email} into a contact?`)) return;
    setConverting(lead.id);
    try {
      const result = await api.post<{ contact: { id: number }; created_contact: boolean }>(
        `/leads/${lead.id}/convert`,
        {},
      );
      toast(
        result.created_contact
          ? "Lead converted — new contact created"
          : "Lead converted — linked to the existing contact",
        "success",
      );
      navigate(`/contacts/${result.contact.id}`);
    } catch (e: any) {
      toast(e?.data?.detail || "Conversion failed", "error");
    } finally {
      setConverting(null);
    }
  };

  const handleExport = async () => {
    try {
      const params: Record<string, string | undefined> = {};
      if (search) params.q = search;
      if (filters.lifecycle_stage) params.lifecycle_stage = filters.lifecycle_stage;
      if (filters.lead_status) params.lead_status = filters.lead_status;
      if (filters.priority) params.priority = filters.priority;
      const data = await api.get<{ rows: any[]; count: number }>("/leads/export", { params });
      downloadCsv(data.rows, "leads-export.csv");
      toast(`Exported ${data.count} lead(s)`, "success");
    } catch (e: any) {
      toast(e?.data?.detail || "Export failed", "error");
    }
  };

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]">
            <IconSparkle className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Leads</h1>
            <p className="text-sm text-[var(--vbase-slate500)]">
              {total} {total === 1 ? "lead" : "leads"}
              {filters.overdue_follow_up ? " · overdue follow-ups" : ""}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleExport} className="vbase-btn-secondary flex items-center gap-1.5">
            <IconDownload className="h-4 w-4" />
            <span>Export CSV</span>
          </button>
          <Link to="/leads/new" className="vbase-btn-primary flex items-center gap-1.5">
            <IconPlus className="h-4 w-4" />
            <span>Add lead</span>
          </Link>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative max-w-xs flex-1">
          <IconSearch className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--vbase-slate400)]" />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search leads, emails, companies…"
            aria-label="Search leads"
            className="vbase-input h-9 pl-9"
          />
        </div>
        <FilterSelect
          label="Stage"
          value={filters.lifecycle_stage || ""}
          onChange={(value) => setFilters({ ...filters, lifecycle_stage: value })}
          options={[{ value: "", label: "Stage" }, ...LEAD_STAGES.map((s) => ({ value: s, label: s }))]}
        />
        <FilterSelect
          label="Status"
          value={filters.lead_status || ""}
          onChange={(value) => setFilters({ ...filters, lead_status: value })}
          options={[
            { value: "", label: "Status" },
            { value: "New", label: "New" },
            { value: "Open", label: "Open" },
            { value: "Working", label: "Working" },
            { value: "Contacted", label: "Contacted" },
            { value: "Nurture", label: "Nurture" },
            { value: "Disqualified", label: "Disqualified" },
            { value: "Converted", label: "Converted" },
          ]}
        />
        <FilterSelect
          label="Priority"
          value={filters.priority || ""}
          onChange={(value) => setFilters({ ...filters, priority: value })}
          options={[{ value: "", label: "Priority" }, ...LEAD_PRIORITIES.map((p) => ({ value: p, label: p }))]}
        />
        <button
          onClick={() => setFilters({ ...filters, overdue_follow_up: !filters.overdue_follow_up })}
          aria-pressed={!!filters.overdue_follow_up}
          className={
            filters.overdue_follow_up
              ? "vbase-btn-secondary flex items-center gap-1.5 text-sm"
              : "vbase-btn-ghost flex items-center gap-1.5 text-sm"
          }
        >
          Overdue follow-ups
        </button>
        <button
          onClick={() => setFilters({ ...filters, converted: filters.converted ? undefined : false })}
          aria-pressed={filters.converted === false}
          className={
            filters.converted === false
              ? "vbase-btn-secondary flex items-center gap-1.5 text-sm"
              : "vbase-btn-ghost flex items-center gap-1.5 text-sm"
          }
        >
          Not converted
        </button>
        <button
          onClick={() => {
            setFilters({});
            setSearch("");
          }}
          className="vbase-btn-ghost flex items-center gap-1.5 text-sm"
        >
          <IconX className="h-3.5 w-3.5" />
          Clear
        </button>
      </div>

      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-[var(--vbase-indigo)]/25 bg-[var(--vbase-indigo)]/5 px-4 py-2.5">
          <span className="text-sm font-medium text-[var(--vbase-slate800)]">{selected.size} selected</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => runBulk("archive")}
              disabled={bulkBusy}
              className="vbase-btn-secondary flex items-center gap-1.5 text-sm"
            >
              <IconArchive className="h-4 w-4" />
              <span>Archive</span>
            </button>
            <button
              onClick={() => runBulk("delete")}
              disabled={bulkBusy}
              className="vbase-btn-danger flex items-center gap-1.5 text-sm"
            >
              <IconTrash2 className="h-4 w-4" />
              <span>Delete</span>
            </button>
            <button onClick={() => setSelected(new Set())} className="vbase-btn-ghost text-sm">
              Clear
            </button>
          </div>
        </div>
      )}

      <div className="vbase-card flex flex-1 flex-col overflow-hidden">
        {loading && leads.length === 0 ? (
          <div className="flex h-40 items-center justify-center text-sm text-[var(--vbase-slate500)]">
            Loading leads…
          </div>
        ) : leads.length === 0 ? (
          <div className="flex-1">
            <EmptyState
              icon="contact"
              title="No leads yet"
              description="Add a lead by hand, or import a spreadsheet from the Import Center."
              actionLabel="Add lead"
              onAction={() => navigate("/leads/new")}
            />
          </div>
        ) : (
          <>
            <div className="overflow-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)]">
                    <th className="w-10 px-3 py-3">
                      <input
                        type="checkbox"
                        checked={leads.length > 0 && selected.size === leads.length}
                        onChange={toggleSelectAll}
                        aria-label="Select all leads on this page"
                        className="h-4 w-4 rounded border-[var(--vbase-border)] text-[var(--vbase-indigo)]"
                      />
                    </th>
                    {["Lead", "Company", "Stage", "Status", "Priority", "Score", "Follow-up", "Updated"].map(
                      (heading) => (
                        <th
                          key={heading}
                          className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]"
                        >
                          {heading}
                        </th>
                      ),
                    )}
                    <th className="w-12 px-3 py-3"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--vbase-border)]">
                  {leads.map((lead) => (
                    <LeadRow
                      key={lead.id}
                      lead={lead}
                      selected={selected.has(lead.id)}
                      onToggleSelect={() => toggleSelect(lead.id)}
                      onChanged={fetchList}
                      onEdit={() => navigate(`/leads/${lead.id}/edit`)}
                      onOpen={() => navigate(`/leads/${lead.id}`)}
                      onConvert={() => quickConvert(lead)}
                      converting={converting === lead.id}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            <div className="border-t border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-4 py-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-[var(--vbase-slate500)]">
                  {total} {total === 1 ? "lead" : "leads"} total
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1}
                    className="vbase-btn-ghost text-sm disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Previous
                  </button>
                  <span className="text-sm text-[var(--vbase-slate500)]">
                    {page} / {Math.max(1, Math.ceil(total / pageSize))}
                  </span>
                  <button
                    onClick={() => setPage((p) => Math.min(Math.ceil(total / pageSize), p + 1))}
                    disabled={page >= Math.ceil(total / pageSize)}
                    className="vbase-btn-ghost text-sm disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function LeadRow({
  lead,
  selected,
  onToggleSelect,
  onChanged,
  onEdit,
  onOpen,
  onConvert,
  converting,
}: {
  lead: Lead;
  selected: boolean;
  onToggleSelect: () => void;
  onChanged: () => void;
  onEdit: () => void;
  onOpen: () => void;
  onConvert: () => void;
  converting: boolean;
}) {
  const name = lead.display_name || lead.full_name || lead.email || "Lead";
  const overdue =
    lead.next_follow_up_at && new Date(lead.next_follow_up_at).getTime() < Date.now() && !lead.converted_at;

  const archive = async (restore: boolean) => {
    try {
      await api.post(`/leads/${lead.id}/${restore ? "restore" : "archive"}`);
      onChanged();
    } catch (e: any) {
      toast(e?.data?.detail || "Action failed", "error");
      throw e;
    }
  };

  return (
    <tr className="group transition-colors hover:bg-[var(--vbase-bg-alt)]">
      <td className="px-3 py-3">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggleSelect}
          aria-label={`Select ${name}`}
          className="h-4 w-4 rounded border-[var(--vbase-border)] text-[var(--vbase-indigo)]"
        />
      </td>
      <td className="px-3 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Link
              to={`/leads/${lead.id}`}
              title={name}
              className="block max-w-[200px] truncate font-medium text-[var(--vbase-slate900)] hover:text-[var(--vbase-indigo)]"
            >
              {name}
            </Link>
            {lead.do_not_contact && (
              <span className="inline-flex h-5 items-center rounded-full border border-[var(--vbase-red)]/30 bg-[var(--vbase-red)]/10 px-2 text-[11px] font-medium text-[var(--vbase-red)]">
                Do not contact
              </span>
            )}
            {lead.converted_at && (
              <span className="inline-flex h-5 items-center rounded-full border border-[var(--vbase-green)]/30 bg-[var(--vbase-green)]/10 px-2 text-[11px] font-medium text-[var(--vbase-green)]">
                Converted
              </span>
            )}
          </div>
          {lead.email && (
            <p className="max-w-[200px] truncate text-xs text-[var(--vbase-slate500)]" title={lead.email}>
              {lead.email}
            </p>
          )}
        </div>
      </td>
      <td className="px-3 py-3">
        <span className="block max-w-[180px] truncate text-sm text-[var(--vbase-slate700)]" title={lead.company_name || undefined}>
          {lead.company_name || <span className="text-[var(--vbase-slate400)]">—</span>}
        </span>
      </td>
      <td className="px-3 py-3">
        <StageChip value={lead.lifecycle_stage} />
      </td>
      <td className="px-3 py-3">
        <span className="text-sm text-[var(--vbase-slate700)]">{lead.lead_status}</span>
      </td>
      <td className="px-3 py-3">
        <PriorityChip value={lead.priority} />
      </td>
      <td className="px-3 py-3">
        <span
          className="inline-flex items-center gap-1 text-sm font-semibold text-[var(--vbase-slate800)]"
          title={lead.score_summary || undefined}
        >
          <IconTarget className="h-3.5 w-3.5 text-[var(--vbase-slate400)]" />
          {lead.lead_score}
        </span>
      </td>
      <td className="whitespace-nowrap px-3 py-3">
        {lead.next_follow_up_at ? (
          <span className={overdue ? "text-sm font-medium text-[var(--vbase-red)]" : "text-sm text-[var(--vbase-slate600)]"}>
            {new Date(lead.next_follow_up_at).toLocaleDateString()}
            {overdue && " · overdue"}
          </span>
        ) : (
          <span className="text-sm text-[var(--vbase-slate400)]">—</span>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-[var(--vbase-slate500)]">
        {lead.updated_at ? new Date(lead.updated_at).toLocaleDateString() : "—"}
      </td>
      <td className="px-3 py-3">
        <div className="flex items-center gap-1">
          {!lead.converted_at && (
            <button
              onClick={onConvert}
              disabled={converting}
              title="Convert to contact"
              aria-label={`Convert ${name}`}
              className="vbase-btn vbase-btn-icon-sm vbase-btn-ghost text-[var(--vbase-slate500)]"
            >
              <IconArrowRightLeft className="h-3.5 w-3.5" />
            </button>
          )}
          <EntityActions
            entityType="lead"
            name={name}
            archived={lead.is_archived}
            onOpen={onOpen}
            onEdit={onEdit}
            onArchive={async () => {
              await archive(false);
            }}
            onRestore={async () => {
              await archive(true);
            }}
            onDelete={async () => {
              await api.delete(`/leads/${lead.id}`);
              onChanged();
            }}
          />
        </div>
      </td>
    </tr>
  );
}

function StageChip({ value }: { value: string }) {
  const tones: Record<string, string> = {
    New: "border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] text-[var(--vbase-slate600)]",
    Working: "border-[var(--vbase-indigo)]/30 bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]",
    Qualified: "border-[var(--vbase-green)]/30 bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]",
    Unqualified: "border-[var(--vbase-red)]/30 bg-[var(--vbase-red)]/10 text-[var(--vbase-red)]",
    Nurture: "border-[var(--vbase-amber)]/30 bg-[var(--vbase-amber)]/10 text-[var(--vbase-amber)]",
    Converted: "border-[var(--vbase-green)]/30 bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${
        tones[value] || tones.New
      }`}
    >
      {value}
    </span>
  );
}

function PriorityChip({ value }: { value: string }) {
  const tones: Record<string, string> = {
    Low: "text-[var(--vbase-slate500)]",
    Medium: "text-[var(--vbase-slate700)]",
    High: "text-[var(--vbase-amber)]",
    Urgent: "text-[var(--vbase-red)]",
  };
  return <span className={`text-sm font-medium ${tones[value] || tones.Medium}`}>{value}</span>;
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label={label}
      className="vbase-select h-9 max-w-[150px] text-sm"
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
