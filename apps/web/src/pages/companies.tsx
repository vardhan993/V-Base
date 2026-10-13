import { useState, useEffect, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { IconPlus, IconSearch, IconRefreshCcw, IconDownload, IconMoreHorizontal, IconX, IconBuilding2, IconLink } from "@/lib/icons";
import { api } from "@/lib/api";
import { Company } from "@/lib/types";
import { downloadCsv } from "@/lib/download";
import { toast } from "@/lib/store";

export function CompaniesPage() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<any>({});
  const [sort] = useState<{field:string; order:string}>({field:"updated_at", order:"desc"});
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const params:any = { page, page_size: pageSize, sort: sort.field, order: sort.order };
      if (search) params.q = search;
      if (filters.industry) params.industry = filters.industry;
      if (filters.country) params.country = filters.country;
      if (filters.city) params.city = filters.city;
      if (filters.employee_min != null) params.employee_min = filters.employee_min;
      if (filters.employee_max != null) params.employee_max = filters.employee_max;
      if (filters.funding_stage) params.funding_stage = filters.funding_stage;
      if (filters.company_size) params.company_size = filters.company_size;
      const data = await api.get<{ items: Company[]; total: number }>("/companies", { params });
      setCompanies(data.items);
      setTotal(data.total);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, [page, pageSize, search, filters, sort]);

  useEffect(() => { fetchList(); }, [fetchList]);

  const handleExport = async () => {
    const data = await api.get<{ rows: any[]; count: number }>("/companies/export", { params: { industry: filters.industry, country: filters.country, city: filters.city } });
    downloadCsv(data.rows, "companies-export.csv");
    toast("Export started", "success");
  };

  if (loading && companies.length === 0) return <Skeleton />;

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Companies</h1>
        <div className="flex items-center gap-2">
          <button onClick={handleExport} className="vbase-btn-secondary flex items-center gap-1.5"><IconDownload className="h-4 w-4" /><span>Export CSV</span></button>
          <button onClick={() => { window.location.hash = "/import"; toast("Use Import Center to add companies from CSV/XLSX", "success"); }} className="vbase-btn-primary flex items-center gap-1.5"><IconPlus className="h-4 w-4" /><span>Add company</span></button>
        </div>
      </div>

      <FiltersBar search={search} onSearch={setSearch} filters={filters} onFilters={setFilters} />

      <div className="vbase-card flex-1 flex flex-col overflow-hidden">
        <table className="vbase-table">
          <thead>
            <tr>
              <th className="w-10">
                <input type="checkbox" checked={selected.size === companies.length && companies.length > 0} onChange={() => setSelected(selected.size === companies.length ? new Set() : new Set(companies.map(c => c.id)))} className="h-4 w-4 rounded border-[var(--vbase-border)]" />
              </th>
              <th className="sticky left-10">Name</th>
              <th>Website</th>
              <th>Industry</th>
              <th>Employees</th>
              <th>Location</th>
              <th>LinkedIn</th>
              <th>Contacts</th>
              <th>Quality</th>
              <th>Updated</th>
              <th className="w-10"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--vbase-border)]">
            {companies.map((c) => (
              <tr key={c.id} className={selected.has(c.id) ? "bg-[var(--vbase-indigo)]/5" : ""}>
                <td className="sticky left-10">
                  <input type="checkbox" checked={selected.has(c.id)} onChange={() => { const next = new Set(selected); next.has(c.id) ? next.delete(c.id) : next.add(c.id); setSelected(next); }} className="h-4 w-4 rounded border-[var(--vbase-border)]" />
                </td>
                <td className="sticky left-10">
                  <div className="flex items-center gap-2">
                    <div className="h-7 w-7 flex items-center justify-center rounded-md bg-[var(--vbase-bg-alt)] text-[var(--vbase-slate600)]">
                      <IconBuilding2 className="h-4 w-4" />
                    </div>
                    <div>
                      <p className="font-medium text-[var(--vbase-slate900)]">{c.name}</p>
                      {c.domain && <p className="text-xs text-[var(--vbase-slate500)]">{c.domain}</p>}
                    </div>
                  </div>
                </td>
                <td className="text-[var(--vbase-slate700)]">
                  {c.website ? <a href={c.website} target="_blank" rel="noreferrer" className="text-[var(--vbase-indigo)] hover:underline">{c.website}</a> : <span className="text-[var(--vbase-slate400)]">—</span>}
                </td>
                <td>{c.industry || <span className="text-[var(--vbase-slate400)]">—</span>}</td>
                <td>{c.employee_count != null ? formatNumber(c.employee_count) : <span className="text-[var(--vbase-slate400)]">—</span>}</td>
                <td>
                  {c.city && <div className="text-[var(--vbase-slate800)]">{c.city}</div>}
                  {c.country && <div className="text-xs text-[var(--vbase-slate500)]">{c.country}</div>}
                  {(!c.city && !c.country) && <span className="text-[var(--vbase-slate400)]">—</span>}
                </td>
                <td>
                  {c.linkedin_url ? <a href={c.linkedin_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-[var(--vbase-indigo)] hover:underline text-xs"><IconLink className="h-3 w-3" />LinkedIn</a> : <span className="text-[var(--vbase-slate400)]">—</span>}
                </td>
                <td>{c.contact_count != null ? <span className="font-medium">{c.contact_count}</span> : <span className="text-[var(--vbase-slate400)]">—</span>}</td>
                <td><QualityBadge score={c.data_quality_score} /></td>
                <td className="text-[var(--vbase-slate500)]">{c.updated_at ? new Date(c.updated_at).toLocaleDateString() : <span className="text-[var(--vbase-slate400)]">—</span>}</td>
                <td className="relative">
                  <div className="flex h-full items-center">
                    <div className="flex items-center gap-1">
                      <Link to={`/companies/${c.id}`} className="flex h-8 w-8 items-center justify-center rounded-md text-[var(--vbase-slate500)] transition-colors hover:bg-[var(--vbase-bg-alt)] hover:text-[var(--vbase-slate700)]" title="View">
                        <IconMoreHorizontal className="h-4 w-4" />
                      </Link>
                    </div>
                  </div>
                </td>
              </tr>
            ))}
            {!companies.length && <EmptyRow label="No companies yet" />}
          </tbody>
        </table>
        <div className="border-t border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-4 py-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-[var(--vbase-slate500)]">{total} companies</span>
            <div className="flex items-center gap-2">
              <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page <= 1} className="vbase-btn-ghost flex items-center gap-1"><IconRefreshCcw className="h-4 w-4" /><span>Previous</span></button>
              <span className="text-sm text-[var(--vbase-slate500)]">{page} / {Math.max(1, Math.ceil(total / pageSize))}</span>
              <button onClick={() => setPage(Math.min(Math.ceil(total / pageSize), page + 1))} disabled={page >= Math.ceil(total / pageSize)} className="vbase-btn-ghost flex items-center gap-1"><span>Next</span><IconRefreshCcw className="h-4 w-4 -scale-x-100" /></button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="flex h-64 flex-col gap-4">
      <div className="h-8 w-48 rounded-md bg-[var(--vbase-slate200)] dark:bg-[var(--vbase-slate700)]" />
      <div className="h-4 w-96 rounded bg-[var(--vbase-slate200)] dark:bg-[var(--vbase-slate700)]" />
    </div>
  );
}

function EmptyRow({ label }: { label: string }) {
  return (
    <tr className="hover:bg-transparent">
      <td colSpan={10} className="px-4 py-12 text-center text-sm text-[var(--vbase-slate500)]">
        <div className="flex flex-col items-center gap-2">
          <IconBuilding2 className="h-8 w-8 text-[var(--vbase-slate300)]" />
          <span>{label}</span>
          <button onClick={() => { window.location.hash = "/import"; }} className="vbase-btn-primary mt-2 flex items-center gap-1.5"><IconPlus className="h-4 w-4" /><span>Add company</span></button>
        </div>
      </td>
    </tr>
  );
}

function FiltersBar({ search, onSearch, filters, onFilters }: any) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="relative flex-1 max-w-xs">
        <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--vbase-slate400)]" />
        <input type="search" value={search} onChange={(e) => onSearch(e.target.value)} placeholder="Search companies…" className="vbase-input pl-9" />
      </div>
      <FilterDropdowns filters={filters} onFilters={onFilters} />
      <button onClick={() => onFilters({})} className="vbase-btn-ghost flex items-center gap-1.5 text-sm"><IconX className="h-3.5 w-3.5" /> Clear</button>
    </div>
  );
}

function FilterDropdowns({ filters, onFilters }: any) {
  const industries = useMemo(() => ["SaaS", "FinTech", "Healthcare", "EdTech", "E-commerce", "Enterprise", "AI/ML", "Gaming", "Media", "Other"], []);
  return (
    <div className="flex items-center gap-2">
      <select value={filters.industry || ""} onChange={(e) => onFilters({...filters, industry: e.target.value})} className="vbase-select max-w-[160px]">
        <option value="">Industry</option>
        {industries.map(i => <option key={i} value={i}>{i}</option>)}
      </select>
      <select value={filters.country || ""} onChange={(e) => onFilters({...filters, country: e.target.value})} className="vbase-select max-w-[140px]">
        <option value="">Country</option>
        {["United States", "India", "United Kingdom", "Canada", "Germany", "Singapore", "Other"].map(c => <option key={c} value={c}>{c}</option>)}
      </select>
      <select value={filters.company_size || ""} onChange={(e) => onFilters({...filters, company_size: e.target.value})} className="vbase-select max-w-[140px]">
        <option value="">Company size</option>
        {["1-10", "11-50", "51-200", "201-500", "501-1000", "1000+"].map(s => <option key={s} value={s}>{s}</option>)}
      </select>
    </div>
  );
}

function formatNumber(n: number) {
  if (n >= 1000000) return (n / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  return String(n);
}

function QualityBadge({ score }: { score: number }) {
  return <div className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${score >= 70 ? "bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]" : score >= 40 ? "bg-[var(--vbase-amber)]/10 text-[var(--vbase-amber)]" : "bg-[var(--vbase-red)]/10 text-[var(--vbase-red)]"}`}>{score}</div>;
}

