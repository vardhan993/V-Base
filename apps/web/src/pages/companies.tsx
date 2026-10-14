import { useState, useEffect, useCallback } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  IconPlus,
  IconSearch,
  IconRefreshCcw,
  IconDownload,
  IconX,
  IconBuilding2,
  IconLink,
  IconUsers,
  IconArchive,
  IconTrash2,
} from "@/lib/icons";
import { api } from "@/lib/api";
import { Company } from "@/lib/types";
import { downloadCsv } from "@/lib/download";
import { EntityActions, EmptyState } from "@/components/crm";
import { toast } from "@/lib/store";

export function CompaniesPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [loading, setLoading] = useState(false);
  // Deep links (topbar search, command palette) arrive as #/companies?search=…
  const [search, setSearch] = useState(() => new URLSearchParams(location.search).get("search")?.trim() ?? "");
  const [filters, setFilters] = useState<CompanyFilters>({});
  const [sort] = useState<{ field: string; order: string }>({
    field: "updated_at",
    order: "desc",
  });
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const params = buildCompanyListParams({ page, pageSize, search, filters, sort });
      const data = await api.get<{ items: Company[]; total: number }>("/companies", { params });
      setCompanies(data.items);
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
      prev.size === companies.length && companies.length > 0 ? new Set() : new Set(companies.map((c) => c.id))
    );
  };

  const runBulk = async (action: "archive" | "delete") => {
    if (selected.size === 0 || bulkBusy) return;
    if (action === "delete" && !window.confirm(`Delete ${selected.size} compan${selected.size === 1 ? "y" : "ies"}? Linked contacts are kept but detached. This cannot be undone.`)) {
      return;
    }
    setBulkBusy(true);
    const ids = [...selected];
    let ok = 0;
    let failed = 0;
    for (const id of ids) {
      try {
        if (action === "archive") await api.post(`/companies/${id}/archive`);
        else await api.delete(`/companies/${id}`);
        ok += 1;
      } catch {
        failed += 1;
      }
    }
    setSelected(new Set());
    setBulkBusy(false);
    if (failed) toast(`${ok} ${action}d, ${failed} failed`, "error");
    else toast(`${ok} compan${ok === 1 ? "y" : "ies"} ${action}d`, "success");
    fetchList();
  };

  const handleExport = async () => {
    try {
      const data = await api.get<{ rows: any[]; count: number }>("/companies/export", {
        params: buildCompanyExportParams(filters),
      });
      downloadCsv(data.rows, "companies-export.csv");
      toast("Export started", "success");
    } catch (e: any) {
      toast(e?.data?.detail || "Export failed", "error");
    }
  };

  if (loading && companies.length === 0) {
    return <CompanySkeleton />;
  }

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]">
            <IconBuilding2 className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Companies</h1>
            <p className="text-sm text-[var(--vbase-slate500)]">
              {total} {total === 1 ? "company" : "companies"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleExport} className="vbase-btn-secondary flex items-center gap-1.5">
            <IconDownload className="h-4 w-4" />
            <span>Export CSV</span>
          </button>
          <Link to="/companies/new" className="vbase-btn-primary flex items-center gap-1.5">
            <IconPlus className="h-4 w-4" />
            <span>Add company</span>
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
        {companies.length === 0 ? (
          <div className="flex-1">
            <EmptyState
              icon="company"
              title="No companies yet"
              description="Import a CSV or spreadsheet to start building your company base."
              actionLabel="Add company"
              onAction={() => navigate("/companies/new")}
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
                        checked={companies.length > 0 && selected.size === companies.length}
                        onChange={toggleSelectAll}
                        aria-label="Select all companies on this page"
                        className="h-4 w-4 rounded border-[var(--vbase-border)] text-[var(--vbase-indigo)]"
                      />
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Company
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Domain
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Website
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Industry
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Size
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Location
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
                      Contacts
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
                  {companies.map((company) => (
                    <CompanyRow
                      key={company.id}
                      company={company}
                      selected={selected.has(company.id)}
                      onToggleSelect={() => toggleSelect(company.id)}
                      onChanged={fetchList}
                      onEdit={() => navigate(`/companies/${company.id}/edit`)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            <div className="border-t border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-4 py-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-[var(--vbase-slate500)]">
                  {total} {total === 1 ? "company" : "companies"} total
                </span>
                <div className="flex items-center gap-2">
                  <CRMButton
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1}
                    label="Previous"
                  />
                  <span className="text-sm text-[var(--vbase-slate500)]">
                    {page} / {Math.max(1, Math.ceil(total / pageSize))}
                  </span>
                  <CRMButton
                    onClick={() => setPage((p) => Math.min(Math.ceil(total / pageSize), p + 1))}
                    disabled={page >= Math.ceil(total / pageSize)}
                    label="Next"
                    rightIcon
                  />
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function CompanyRow({
  company,
  selected,
  onToggleSelect,
  onChanged,
  onEdit,
}: {
  company: Company;
  selected: boolean;
  onToggleSelect: () => void;
  onChanged: () => void;
  onEdit: () => void;
}) {
  return (
    <tr className="group transition-colors hover:bg-[var(--vbase-bg-alt)]">
      <td className="px-3 py-3">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggleSelect}
          aria-label={`Select ${company.name}`}
          className="h-4 w-4 rounded border-[var(--vbase-border)] text-[var(--vbase-indigo)]"
        />
      </td>
      <td className="px-3 py-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-[var(--vbase-bg-alt)] text-[var(--vbase-slate600)]">
            <IconBuilding2 className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 min-w-0">
              <Link
                to={`/companies/${company.id}`}
                title={company.name}
                className="group/row block max-w-[220px] truncate font-medium text-[var(--vbase-slate900)] transition-colors hover:text-[var(--vbase-indigo)]"
              >
                {company.name}
              </Link>
              {company.is_archived && (
                <span className="inline-flex h-5 flex-shrink-0 items-center rounded-full border border-[var(--vbase-border)] bg-[var(--vbase-slate100)] px-2 text-[11px] font-medium uppercase tracking-wide text-[var(--vbase-slate500)]">
                  Archived
                </span>
              )}
            </div>
            {company.domain && (
              <p className="max-w-[220px] truncate text-xs text-[var(--vbase-slate500)]" title={company.domain}>
                {company.domain}
              </p>
            )}
          </div>
        </div>
      </td>
      <td className="px-3 py-3">
        <span className="block max-w-[160px] truncate text-sm text-[var(--vbase-slate700)]" title={company.domain || undefined}>
          {company.domain || <span className="text-[var(--vbase-slate400)]">—</span>}
        </span>
      </td>
      <td className="px-3 py-3">
        {company.website ? (
          <a
            href={company.website}
            target="_blank"
            rel="noreferrer"
            title={company.website}
            className="inline-flex min-w-0 max-w-[160px] items-center gap-1 text-sm text-[var(--vbase-indigo)] hover:underline"
          >
            <span className="block truncate">{company.website}</span>
            <IconLink className="h-3 w-3 flex-shrink-0" />
          </a>
        ) : (
          <span className="text-sm text-[var(--vbase-slate400)]">—</span>
        )}
      </td>
      <td className="px-3 py-3">
        <span className="block max-w-[140px] truncate text-sm text-[var(--vbase-slate700)]" title={company.industry || undefined}>
          {company.industry || <span className="text-[var(--vbase-slate400)]">—</span>}
        </span>
      </td>
      <td className="px-3 py-3">
        <span className="whitespace-nowrap text-sm text-[var(--vbase-slate700)]">
          {company.company_size || <span className="text-[var(--vbase-slate400)]">—</span>}
        </span>
      </td>
      <td className="px-3 py-3">
        <div className="max-w-[160px] truncate text-sm" title={[company.city, company.country].filter(Boolean).join(", ") || undefined}>
          {company.city ? (
            <>
              <span className="text-[var(--vbase-slate800)]">{company.city}</span>
              {company.country && <span className="ml-1 text-[var(--vbase-slate500)]">· {company.country}</span>}
            </>
          ) : (
            <span className="text-[var(--vbase-slate400)]">—</span>
          )}
        </div>
      </td>
      <td className="px-3 py-3">
        <div className="flex items-center gap-1.5">
          <IconUsers className="h-3.5 w-3.5 text-[var(--vbase-slate500)]" />
          <span className="font-medium text-sm text-[var(--vbase-slate800)]">
            {company.contact_count ?? <span className="text-[var(--vbase-slate400)]">—</span>}
          </span>
        </div>
      </td>
      <td className="px-3 py-3">
        <QualityChip score={company.data_quality_score} />
      </td>
      <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-[var(--vbase-slate500)]">
        {company.updated_at ? new Date(company.updated_at).toLocaleDateString() : "—"}
      </td>
      <td className="px-3 py-3">
        <EntityActions
          entityType="company"
          id={company.id}
          name={company.name}
          archived={company.is_archived}
          onEdit={onEdit}
          onArchive={async () => {
            await archiveCompany(company.id);
            onChanged();
          }}
          onRestore={async () => {
            await restoreCompany(company.id);
            onChanged();
          }}
          onDelete={async () => {
            await deleteCompany(company.id);
            onChanged();
          }}
        />
      </td>
    </tr>
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
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${colors[rank]}`}
    >
      {score}
    </span>
  );
}

function CRMButton({
  onClick,
  disabled,
  label,
  rightIcon,
}: {
  onClick: () => void;
  disabled: boolean;
  label: string;
  rightIcon?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`vbase-btn-ghost flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed ${
        rightIcon ? "sm:flex-row-reverse" : ""
      }`}
    >
      <IconRefreshCcw className="h-4 w-4" style={{ transform: rightIcon ? "scaleX(-1)" : undefined }} />
      <span>{label}</span>
    </button>
  );
}

function archiveCompany(id: number) {
  return api.post(`/companies/${id}/archive`).catch((e: any) => {
    toast(e?.data?.detail || "Archive failed", "error");
    throw e;
  });
}

function restoreCompany(id: number) {
  return api.post(`/companies/${id}/restore`).catch((e: any) => {
    toast(e?.data?.detail || "Restore failed", "error");
    throw e;
  });
}

function deleteCompany(id: number) {
  return api.delete(`/companies/${id}`).catch((e: any) => {
    toast(e?.data?.detail || "Delete failed", "error");
    throw e;
  });
}

interface CompanyFilters {
  industry?: string;
  country?: string;
  city?: string;
  employee_min?: number;
  employee_max?: number;
  funding_stage?: string;
  company_size?: string;
}

function buildCompanyListParams({
  page,
  pageSize,
  search,
  filters,
  sort,
}: {
  page: number;
  pageSize: number;
  search: string;
  filters: CompanyFilters;
  sort: { field: string; order: string };
}) {
  const params: any = { page, page_size: pageSize, sort: sort.field, order: sort.order };
  if (search) params.q = search;
  if (filters.industry) params.industry = filters.industry;
  if (filters.country) params.country = filters.country;
  if (filters.city) params.city = filters.city;
  if (filters.employee_min != null) params.employee_min = filters.employee_min;
  if (filters.employee_max != null) params.employee_max = filters.employee_max;
  if (filters.funding_stage) params.funding_stage = filters.funding_stage;
  if (filters.company_size) params.company_size = filters.company_size;
  return params;
}

function buildCompanyExportParams(filters: CompanyFilters) {
  const params: any = {};
  if (filters.industry) params.industry = filters.industry;
  if (filters.country) params.country = filters.country;
  if (filters.city) params.city = filters.city;
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
  filters: CompanyFilters;
  onFilters: (filters: CompanyFilters) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="relative flex-1 max-w-xs">
        <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--vbase-slate400)]" />
        <input
          type="search"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Search companies, domains, industries…"
          className="vbase-input pl-9 h-9"
        />
      </div>
      <FilterSelect
        value={filters.industry || ""}
        onChange={(value) => onFilters({ ...filters, industry: value })}
        options={[
          { value: "", label: "Industry" },
          { value: "SaaS", label: "SaaS" },
          { value: "FinTech", label: "FinTech" },
          { value: "Healthcare", label: "Healthcare" },
          { value: "EdTech", label: "EdTech" },
          { value: "AI/ML", label: "AI/ML" },
          { value: "Enterprise", label: "Enterprise" },
        ]}
      />
      <FilterSelect
        value={filters.country || ""}
        onChange={(value) => onFilters({ ...filters, country: value })}
        options={[
          { value: "", label: "Country" },
          { value: "United States", label: "United States" },
          { value: "India", label: "India" },
          { value: "United Kingdom", label: "United Kingdom" },
          { value: "Canada", label: "Canada" },
          { value: "Germany", label: "Germany" },
        ]}
      />
      <FilterSelect
        value={filters.company_size || ""}
        onChange={(value) => onFilters({ ...filters, company_size: value })}
        options={[
          { value: "", label: "Size" },
          { value: "1-10", label: "1-10" },
          { value: "11-50", label: "11-50" },
          { value: "51-200", label: "51-200" },
          { value: "201-500", label: "201-500" },
          { value: "501-1000", label: "501-1000" },
          { value: "1000+", label: "1000+" },
        ]}
      />
      <button
        onClick={() => onFilters({})}
        className="vbase-btn-ghost flex items-center gap-1.5 text-sm"
      >
        <IconX className="h-3.5 w-3.5" />
        Clear
      </button>
    </div>
  );
}

function FilterSelect({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="vbase-select h-9 max-w-[140px] text-sm"
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

function CompanySkeleton() {
  return (
    <div className="flex h-64 flex-col gap-4">
      <div className="h-8 w-48 rounded-md bg-[var(--vbase-slate200)]" />
      <div className="h-4 w-96 rounded bg-[var(--vbase-slate200)]" />
    </div>
  );
}
