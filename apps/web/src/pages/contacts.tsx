import { useState, useEffect, useCallback, useRef } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { IconPlus, IconSearch, IconDownload, IconX, IconUsers, IconBuilding2, IconMail, IconLink, IconRefreshCcw, IconArchive, IconTrash2 } from "@/lib/icons";
import { api } from "@/lib/api";
import { Contact } from "@/lib/types";
import { downloadCsv } from "@/lib/download";
import { EntityActions, EmptyState, ContactAvatar, ClippedText, StageBadge, PhoneCell } from "@/components/crm";
import { CRM_STAGES } from "@/lib/crm";
import { toast } from "@/lib/store";

export function ContactPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [loading, setLoading] = useState(false);
  // Deep links (topbar search, command palette) arrive as #/contacts?search=…
  const [search, setSearch] = useState(() => new URLSearchParams(location.search).get("search")?.trim() ?? "");
  const [filters, setFilters] = useState<ContactFilters>({});
  const [sort] = useState<{ field: string; order: string }>({ field: "updated_at", order: "desc" });
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const params = buildContactListParams({ page, pageSize, search, filters, sort });
      const data = await api.get<{ items: Contact[]; total: number }>("/contacts", { params });
      setContacts(data.items);
      setTotal(data.total);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, filters, sort]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  useEffect(() => {
    setSelected(new Set());
  }, [page, search, filters]);

  // Keep the list in step with the URL: a search issued while this page is
  // already mounted (command palette, browser back) must still apply.
  useEffect(() => {
    const q = new URLSearchParams(location.search).get("search")?.trim() ?? "";
    if (q) setSearch(q);
  }, [location.search]);

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
      prev.size === contacts.length && contacts.length > 0 ? new Set() : new Set(contacts.map((c) => c.id))
    );
  };

  const runBulk = async (action: "archive" | "delete") => {
    if (selected.size === 0 || bulkBusy) return;
    if (action === "delete" && !window.confirm(`Delete ${selected.size} contact${selected.size === 1 ? "" : "s"}? This cannot be undone.`)) {
      return;
    }
    setBulkBusy(true);
    const ids = [...selected];
    let ok = 0;
    let failed = 0;
    for (const id of ids) {
      try {
        if (action === "archive") await api.post(`/contacts/${id}/archive`);
        else await api.delete(`/contacts/${id}`);
        ok += 1;
      } catch {
        failed += 1;
      }
    }
    setSelected(new Set());
    setBulkBusy(false);
    if (failed) toast(`${ok} ${action}d, ${failed} failed`, "error");
    else toast(`${ok} contact${ok === 1 ? "" : "s"} ${action}d`, "success");
    fetchList();
  };

  const handleExport = async () => {
    try {
      const data = await api.get<{ rows: any[]; count: number }>("/contacts/export", {
        params: buildContactExportParams({ search, filters }),
      });
      downloadCsv(data.rows, "contacts-export.csv");
      toast("Export started", "success");
    } catch (e: any) {
      toast(e?.data?.detail || "Export failed", "error");
    }
  };

  if (loading && contacts.length === 0) {
    return <ContactSkeleton />;
  }

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]">
            <IconUsers className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Contacts</h1>
            <p className="text-sm text-[var(--vbase-slate500)]">{total} contact{total !== 1 ? "s" : ""}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleExport} className="vbase-btn-secondary flex items-center gap-1.5">
            <IconDownload className="h-4 w-4" />
            <span>Export CSV</span>
          </button>
          <Link to="/contacts/new" className="vbase-btn-primary flex items-center gap-1.5">
            <IconPlus className="h-4 w-4" />
            <span>Add contact</span>
          </Link>
        </div>
      </div>

      <FiltersBarCRM search={search} onSearch={setSearch} filters={filters} onFilters={setFilters} />

      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-[var(--vbase-indigo)]/25 bg-[var(--vbase-indigo)]/5 px-4 py-2.5">
          <span className="text-sm font-medium text-[var(--vbase-slate800)]">
            {selected.size} selected
          </span>
          <div className="flex items-center gap-2">
            <button onClick={() => runBulk("archive")} disabled={bulkBusy} className="vbase-btn-secondary flex items-center gap-1.5 text-sm">
              <IconArchive className="h-4 w-4" />
              <span>Archive</span>
            </button>
            <button onClick={() => runBulk("delete")} disabled={bulkBusy} className="vbase-btn-danger flex items-center gap-1.5 text-sm">
              <IconTrash2 className="h-4 w-4" />
              <span>Delete</span>
            </button>
            <button onClick={() => setSelected(new Set())} className="vbase-btn-ghost text-sm">
              Clear
            </button>
          </div>
        </div>
      )}

      <div className="vbase-card flex-1 flex flex-col overflow-hidden">
        {contacts.length === 0 ? (
          <div className="flex-1">
            <EmptyState
              icon="contact"
              title="No contacts yet"
              description="Import a CSV or spreadsheet to start building your contact base."
              actionLabel="Add contact"
              onAction={() => navigate("/contacts/new")}
            />
          </div>
        ) : (
          <>
            <div className="overflow-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)]">
                    <th className="w-10 px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      <input
                        type="checkbox"
                        checked={contacts.length > 0 && selected.size === contacts.length}
                        onChange={toggleSelectAll}
                        aria-label="Select all contacts on this page"
                        className="h-4 w-4 rounded border-[var(--vbase-border)] text-[var(--vbase-indigo)]"
                      />
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Contact
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Job title
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Company
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Stage
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Email
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Email status
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Phone
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Phone status
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      LinkedIn
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Quality
                    </th>
                    <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Updated
                    </th>
                    <th className="w-12 px-3 py-3"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--vbase-border)]">
                  {contacts.map((contact) => (
                    <ContactRow
                      key={contact.id}
                      contact={contact}
                      selected={selected.has(contact.id)}
                      onToggleSelect={() => toggleSelect(contact.id)}
                      onChanged={fetchList}
                      onEdit={() => navigate(`/contacts/${contact.id}/edit`)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            <div className="border-t border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-4 py-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-[var(--vbase-slate500)]">{total} contact{total !== 1 ? "s" : ""} total</span>
                <div className="flex items-center gap-2">
                  <CRMButton onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} label="Previous" />
                  <span className="text-sm text-[var(--vbase-slate500)]">
                    {page} / {Math.max(1, Math.ceil(total / pageSize))}
                  </span>
                  <CRMButton onClick={() => setPage((p) => Math.min(Math.ceil(total / pageSize), p + 1))} disabled={page >= Math.ceil(total / pageSize)} label="Next" rightIcon />
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ContactRow({
  contact,
  selected,
  onToggleSelect,
  onChanged,
  onEdit,
}: {
  contact: Contact;
  selected: boolean;
  onToggleSelect: () => void;
  onChanged: () => void;
  onEdit: () => void;
}) {
  const name = contact.display_name || contact.full_name || contact.email || "Contact";
  const companyName = contact.company?.name || contact.company_name || null;

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
        <div className="flex items-center gap-3 min-w-0">
          <ContactAvatar name={name} size={34} />
          <div className="min-w-0">
            <Link
              to={`/contacts/${contact.id}`}
              title={name}
              className="group/row block max-w-[220px] truncate font-medium text-[var(--vbase-slate900)] transition-colors hover:text-[var(--vbase-indigo)]"
            >
              {name}
            </Link>
            {contact.email && (
              <p className="max-w-[220px] truncate text-xs text-[var(--vbase-slate500)]" title={contact.email}>
                {contact.email}
              </p>
            )}
          </div>
        </div>
      </td>
      <td className="px-3 py-3">
        <ClippedText maxWidth="max-w-[160px]" className="text-sm text-[var(--vbase-slate700)]">
          {contact.job_title || "—"}
        </ClippedText>
      </td>
      <td className="px-3 py-3">
        <CompanyChip name={companyName} />
      </td>
      <td className="px-3 py-3">
        <StageBadge stage={contact.stage} />
      </td>
      <td className="px-3 py-3">
        {contact.email ? (
          <span className="inline-flex min-w-0 items-center gap-1.5 text-sm text-[var(--vbase-slate800)]">
            <IconMail className="h-3.5 w-3.5 flex-shrink-0 text-[var(--vbase-slate500)]" />
            <span className="block max-w-[200px] truncate" title={contact.email}>
              {contact.email}
            </span>
          </span>
        ) : (
          <span className="text-sm text-[var(--vbase-slate400)]">—</span>
        )}
      </td>
      <td className="px-3 py-3">
        <StatusChip status={contact.email_status} />
      </td>
      <td className="px-3 py-3">
        <PhoneCell phone={contact.phone} />
      </td>
      <td className="px-3 py-3">
        <StatusChip status={contact.phone_status} />
      </td>
      <td className="px-3 py-3">
        {contact.linkedin_url ? (
          <a
            href={contact.linkedin_url}
            target="_blank"
            rel="noreferrer"
            title={contact.linkedin_url}
            className="inline-flex items-center gap-1 text-sm text-[var(--vbase-indigo)] hover:underline"
          >
            <IconLink className="h-3.5 w-3.5 flex-shrink-0" />
            LinkedIn
          </a>
        ) : (
          <span className="text-sm text-[var(--vbase-slate400)]">—</span>
        )}
      </td>
      <td className="px-3 py-3">
        <QualityChip score={contact.data_quality_score} />
      </td>
      <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-[var(--vbase-slate500)]">
        {contact.updated_at ? new Date(contact.updated_at).toLocaleDateString() : "—"}
      </td>
      <td className="px-3 py-3">
        <EntityActions
          entityType="contact"
          name={name}
          archived={contact.is_archived}
          onEdit={onEdit}
          onArchive={async () => {
            await archiveContact(contact.id);
            onChanged();
          }}
          onRestore={async () => {
            await restoreContact(contact.id);
            onChanged();
          }}
          onDelete={async () => {
            await deleteContact(contact.id);
            onChanged();
          }}
        />
      </td>
    </tr>
  );
}

function CompanyChip({ name }: { name: string | null }) {
  return (
    <span
      title={name || "No company"}
      className={`inline-flex min-w-0 max-w-[180px] items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium ${
        name
          ? "border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] text-[var(--vbase-slate700)]"
          : "border-dashed border-[var(--vbase-border)] bg-transparent text-[var(--vbase-slate400)]"
      }`}
    >
      <IconBuilding2 className="h-3.5 w-3.5 flex-shrink-0" />
      <span className="block truncate">{name || "No company"}</span>
    </span>
  );
}

function StatusChip({ status }: { status?: string | null }) {
  if (!status) return <span className="text-sm text-[var(--vbase-slate400)]">—</span>;
  const rank =
    status.toLowerCase() === "verified"
      ? "verified"
      : status.toLowerCase() === "pending"
      ? "pending"
      : status.toLowerCase() === "invalid"
      ? "invalid"
      : "unknown";
  const colors = {
    verified: "border-[var(--vbase-green)]/30 bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]",
    pending: "border-[var(--vbase-amber)]/30 bg-[var(--vbase-amber)]/10 text-[var(--vbase-amber)]",
    invalid: "border-[var(--vbase-red)]/30 bg-[var(--vbase-red)]/10 text-[var(--vbase-red)]",
    unknown: "border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] text-[var(--vbase-slate500)]",
  };
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${colors[rank]}`}>
      {status}
    </span>
  );
}

function QualityChip({ score }: { score: number }) {
  const rank = score >= 70 ? "high" : score >= 40 ? "medium" : "low";
  const colors = {
    high: "bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]",
    medium: "bg-[var(--vbase-amber)]/10 text-[var(--vbase-amber)]",
    low: "bg-[var(--vbase-red)]/10 text-[var(--vbase-red)]",
  };
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${colors[rank]}`}>
      {score}
    </span>
  );
}

function CRMButton({ onClick, disabled, label, rightIcon }: { onClick: () => void; disabled: boolean; label: string; rightIcon?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`vbase-btn-ghost flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed ${rightIcon ? "sm:flex-row-reverse" : ""}`}
    >
      <IconRefreshCcw className="h-4 w-4" style={{ transform: rightIcon ? "scaleX(-1)" : undefined }} />
      <span>{label}</span>
    </button>
  );
}

function archiveContact(id: number) {
  return api.post(`/contacts/${id}/archive`).catch((e: any) => {
    toast(e?.data?.detail || "Archive failed", "error");
    throw e;
  });
}

function restoreContact(id: number) {
  return api.post(`/contacts/${id}/restore`).catch((e: any) => {
    toast(e?.data?.detail || "Restore failed", "error");
    throw e;
  });
}

function deleteContact(id: number) {
  return api.delete(`/contacts/${id}`).catch((e: any) => {
    toast(e?.data?.detail || "Delete failed", "error");
    throw e;
  });
}

interface ContactFilters {
  job_title?: string;
  company_name?: string;
  email?: string;
  phone?: string;
  city?: string;
  country?: string;
  email_status?: string;
  phone_status?: string;
  linkedin_available?: boolean | null;
  email_available?: boolean | null;
  phone_available?: boolean | null;
  seniority?: string;
  department?: string;
  stage?: string;
  data_quality_min?: number;
  data_quality_max?: number;
}

function buildContactListParams({
  page,
  pageSize,
  search,
  filters,
  sort,
}: {
  page: number;
  pageSize: number;
  search: string;
  filters: ContactFilters;
  sort: { field: string; order: string };
}) {
  const params: any = { page, page_size: pageSize, sort: sort.field, order: sort.order };
  if (search) params.q = search;
  if (filters.job_title) params.job_title = filters.job_title;
  if (filters.company_name) params.company_name = filters.company_name;
  if (filters.email) params.email = filters.email;
  if (filters.phone) params.phone = filters.phone;
  if (filters.city) params.city = filters.city;
  if (filters.country) params.country = filters.country;
  if (filters.email_status) params.email_status = filters.email_status;
  if (filters.phone_status) params.phone_status = filters.phone_status;
  if (filters.linkedin_available != null) params.linkedin_available = filters.linkedin_available;
  if (filters.email_available != null) params.email_available = filters.email_available;
  if (filters.phone_available != null) params.phone_available = filters.phone_available;
      if (filters.seniority) params.seniority = filters.seniority;
      if (filters.department) params.department = filters.department;
      if (filters.stage) params.stage = filters.stage;
  if (filters.data_quality_min != null) params.data_quality_min = filters.data_quality_min;
  if (filters.data_quality_max != null) params.data_quality_max = filters.data_quality_max;
  return params;
}

function buildContactExportParams({
  search,
  filters,
}: {
  search: string;
  filters: ContactFilters;
}) {
  const params: any = {};
  if (search) params.q = search;
  if (filters.job_title) params.job_title = filters.job_title;
  if (filters.company_name) params.company_name = filters.company_name;
  if (filters.city) params.city = filters.city;
  if (filters.country) params.country = filters.country;
  if (filters.email_status) params.email_status = filters.email_status;
  if (filters.seniority) params.seniority = filters.seniority;
  if (filters.stage) params.stage = filters.stage;
  return params;
}

function FiltersBarCRM({
  search,
  onSearch,
  filters,
  onFilters,
}: {
  search: string;
  onSearch: (value: string) => void;
  filters: ContactFilters;
  onFilters: (filters: ContactFilters) => void;
}) {
  const [moreOpen, setMoreOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!moreOpen) return;
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setMoreOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [moreOpen]);

  const activeCount =
    [filters.job_title, filters.email_status, filters.seniority, filters.stage, filters.company_name, filters.email, filters.phone, filters.city, filters.country, filters.department]
      .filter(Boolean).length +
    (filters.linkedin_available != null ? 1 : 0) +
    (filters.email_available != null ? 1 : 0) +
    (filters.phone_available != null ? 1 : 0) +
    (filters.data_quality_min != null || filters.data_quality_max != null ? 1 : 0);

  return (
    <div className="flex items-center gap-3">
      <div className="flex flex-1 flex-wrap items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--vbase-slate400)]" />
          <input
            type="search"
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            placeholder="Search contacts, emails, phones, companies…"
            className="vbase-input pl-9 h-9"
          />
        </div>
        <FilterSelect
          value={filters.job_title || ""}
          onChange={(value) => onFilters({ ...filters, job_title: value })}
          options={[
            { value: "", label: "Job title" },
            { value: "CEO", label: "CEO" },
            { value: "CTO", label: "CTO" },
            { value: "CFO", label: "CFO" },
            { value: "Founder", label: "Founder" },
            { value: "VP Engineering", label: "VP Engineering" },
            { value: "Product Manager", label: "Product Manager" },
          ]}
        />
        <FilterSelect
          value={filters.email_status || ""}
          onChange={(value) => onFilters({ ...filters, email_status: value })}
          options={[
            { value: "", label: "Email status" },
            { value: "Verified", label: "Verified" },
            { value: "Pending", label: "Pending" },
            { value: "Invalid", label: "Invalid" },
            { value: "Missing", label: "Missing" },
          ]}
        />
        <FilterSelect
          value={filters.seniority || ""}
          onChange={(value) => onFilters({ ...filters, seniority: value })}
          options={[
            { value: "", label: "Seniority" },
            { value: "C-level", label: "C-level" },
            { value: "VP", label: "VP" },
            { value: "Director", label: "Director" },
            { value: "Manager", label: "Manager" },
          ]}
          placeholder="Seniority"
        />
        <FilterSelect
          value={filters.stage || ""}
          onChange={(value) => onFilters({ ...filters, stage: value })}
          options={[{ value: "", label: "Stage" }, ...CRM_STAGES.map((s) => ({ value: s, label: s }))]}
          placeholder="Stage"
        />
        {activeCount > 0 && (
          <button
            type="button"
            onClick={() => onFilters({})}
            className="vbase-btn-ghost flex items-center gap-1.5 text-sm"
          >
            <IconX className="h-3.5 w-3.5" />
            Clear
          </button>
        )}
      </div>

      <div className="relative" ref={ref}>
        <button
          type="button"
          onClick={() => setMoreOpen((v) => !v)}
          className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium transition-colors ${
            activeCount > 0 || moreOpen
              ? "border-[var(--vbase-indigo)] bg-[var(--vbase-indigo)]/5 text-[var(--vbase-indigo)]"
              : "border-[var(--vbase-border)] text-[var(--vbase-slate600)] hover:border-[var(--vbase-indigo)] hover:text-[var(--vbase-indigo)]"
          }`}
        >
          More filters
          {(filters.linkedin_available != null || filters.email_available != null || filters.phone_available != null) && (
            <span className="flex h-4 w-4 items-center justify-center rounded-full border border-current/30 bg-current/10 text-[10px] font-semibold uppercase">
              A
            </span>
          )}
          {(filters.data_quality_min != null || filters.data_quality_max != null) && (
            <span className="flex h-4 w-4 items-center justify-center rounded-full border border-current/30 bg-current/10 text-[10px] font-semibold uppercase">
              Q
            </span>
          )}
        </button>

        {moreOpen && (
          <div
            className="absolute right-0 top-9 z-50 w-72 rounded-lg border border-[var(--vbase-border)] bg-[var(--vbase-bg)] p-4 shadow-[0_10px_30px_-8px_rgba(0,0,0,0.18)]"
          >
            <div className="flex items-center justify-between border-b border-[var(--vbase-border)] pb-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">Advanced</span>
              <button
                type="button"
                onClick={() => {
                  setMoreOpen(false);
                  onFilters({});
                }}
                className="text-xs text-[var(--vbase-indigo)] hover:underline"
              >
                Clear all
              </button>
            </div>

            <div className="mt-3 space-y-4">
              <FilterField label="Company contains">
                <input
                  type="search"
                  value={filters.company_name || ""}
                  onChange={(e) => onFilters({ ...filters, company_name: e.target.value })}
                  placeholder="Acme, Northwind…"
                  className="vbase-input h-8 w-full text-sm"
                />
              </FilterField>

              <FilterField label="Email contains">
                <input
                  type="search"
                  value={filters.email || ""}
                  onChange={(e) => onFilters({ ...filters, email: e.target.value })}
                  placeholder="name@company.com"
                  className="vbase-input h-8 w-full text-sm"
                />
              </FilterField>

              <FilterField label="Phone contains">
                <input
                  type="search"
                  value={filters.phone || ""}
                  onChange={(e) => onFilters({ ...filters, phone: e.target.value })}
                  placeholder="+91 98765 43210"
                  className="vbase-input h-8 w-full text-sm"
                />
              </FilterField>

              <div className="grid grid-cols-2 gap-3">
                <FilterField label="City contains">
                  <input
                    type="search"
                    value={filters.city || ""}
                    onChange={(e) => onFilters({ ...filters, city: e.target.value })}
                    placeholder="Bengaluru, London…"
                    className="vbase-input h-8 w-full text-sm"
                  />
                </FilterField>

                <FilterField label="Country contains">
                  <input
                    type="search"
                    value={filters.country || ""}
                    onChange={(e) => onFilters({ ...filters, country: e.target.value })}
                    placeholder="India, United Kingdom…"
                    className="vbase-input h-8 w-full text-sm"
                  />
                </FilterField>
              </div>

              <FilterField label="Department contains">
                <input
                  type="search"
                  value={filters.department || ""}
                  onChange={(e) => onFilters({ ...filters, department: e.target.value })}
                  placeholder="Engineering, HR…"
                  className="vbase-input h-8 w-full text-sm"
                />
              </FilterField>

              <div className="border-t border-[var(--vbase-border)] pt-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">Availability</p>
                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-sm text-[var(--vbase-slate700)]">
                    <input
                      type="checkbox"
                      checked={filters.linkedin_available === true}
                      onChange={(e) => onFilters({ ...filters, linkedin_available: e.target.checked ? true : null })}
                      className="h-4 w-4 rounded border-[var(--vbase-border)] text-[var(--vbase-indigo)]"
                    />
                    Has LinkedIn profile
                  </label>
                  <label className="flex items-center gap-2 text-sm text-[var(--vbase-slate700)]">
                    <input
                      type="checkbox"
                      checked={filters.email_available === true}
                      onChange={(e) => onFilters({ ...filters, email_available: e.target.checked ? true : null })}
                      className="h-4 w-4 rounded border-[var(--vbase-border)] text-[var(--vbase-indigo)]"
                    />
                    Has email
                  </label>
                  <label className="flex items-center gap-2 text-sm text-[var(--vbase-slate700)]">
                    <input
                      type="checkbox"
                      checked={filters.phone_available === true}
                      onChange={(e) => onFilters({ ...filters, phone_available: e.target.checked ? true : null })}
                      className="h-4 w-4 rounded border-[var(--vbase-border)] text-[var(--vbase-indigo)]"
                    />
                    Has phone
                  </label>
                </div>
              </div>

              <div className="border-t border-[var(--vbase-border)] pt-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">Data quality score</p>
                <div className="flex items-center gap-2">
                  <FilterRangeInput
                    label="From"
                    value={filters.data_quality_min == null ? "" : String(filters.data_quality_min)}
                    onChange={(value) => onFilters({ ...filters, data_quality_min: value ? Number(value) : undefined })}
                  />
                  <span className="text-[var(--vbase-slate400)]">–</span>
                  <FilterRangeInput
                    label="To"
                    value={filters.data_quality_max == null ? "" : String(filters.data_quality_max)}
                    onChange={(value) => onFilters({ ...filters, data_quality_max: value ? Number(value) : undefined })}
                  />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-medium text-[var(--vbase-slate500)]">{label}</label>
      {children}
    </div>
  );
}

function FilterRangeInput({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <div className="flex items-center gap-2">
      <label className="text-xs text-[var(--vbase-slate500)]">{label}</label>
      <input
        type="number"
        min={0}
        max={100}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="vbase-input h-8 w-16 text-sm text-center"
      />
    </div>
  );
}

function FilterSelect({ value, onChange, options, placeholder }: { value: string; onChange: (value: string) => void; options: { value: string; label: string }[]; placeholder?: string }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className="vbase-select h-9 max-w-[140px] text-sm">
      <option value="">{placeholder || options[0]?.label || ""}</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

function ContactSkeleton() {
  return (
    <div className="flex h-64 flex-col gap-4">
      <div className="h-8 w-48 rounded-md bg-[var(--vbase-slate200)]" />
      <div className="h-4 w-96 rounded bg-[var(--vbase-slate200)]" />
    </div>
  );
}
