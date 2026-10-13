import { useState, useEffect, useCallback } from "react";
import { IconPlus, IconSearch, IconDownload, IconMoreHorizontal, IconRefreshCcw as IconRotateCcw, IconX, IconUsers, IconBuilding2, IconMail, IconPhone, IconLink } from "@/lib/icons";
import { api } from "@/lib/api";
import { downloadCsv } from "@/lib/download";
import { Contact } from "@/lib/types";
import { toast } from "@/lib/store";

export function ContactPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
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
      if (filters.data_quality_min != null) params.data_quality_min = filters.data_quality_min;
      if (filters.data_quality_max != null) params.data_quality_max = filters.data_quality_max;
      const data = await api.get<{ items: Contact[]; total: number }>("/contacts", { params });
      setContacts(data.items);
      setTotal(data.total);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, [page, pageSize, search, filters, sort]);

  useEffect(() => { fetchList(); }, [fetchList]);

  const handleExport = async () => {
    const data = await api.get<{ rows: any[]; count: number }>("/contacts/export", { params: { q: search } });
    downloadCsv(data.rows, "contacts-export.csv");
    toast("Export started", "success");
  };

  if (loading && contacts.length === 0) return <Skeleton />;

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Contacts</h1>
        <div className="flex items-center gap-2">
          <button onClick={handleExport} className="vbase-btn-secondary flex items-center gap-1.5"><IconDownload className="h-4 w-4" /><span>Export CSV</span></button>
          <button onClick={() => { window.location.hash = "/import"; toast("Use Import Center to add contacts from CSV/XLSX", "success"); }} className="vbase-btn-primary flex items-center gap-1.5"><IconPlus className="h-4 w-4" /><span>Add contact</span></button>
        </div>
      </div>

      <FiltersBar search={search} onSearch={setSearch} filters={filters} onFilters={setFilters} />

      <div className="vbase-card flex-1 flex flex-col overflow-hidden">
        <div className="overflow-auto">
          <table className="vbase-table">
            <thead>
              <tr>
                <th className="w-10">
                  <input type="checkbox" checked={selected.size === contacts.length && contacts.length > 0} onChange={() => setSelected(selected.size === contacts.length ? new Set() : new Set(contacts.map(c => c.id)))} className="h-4 w-4 rounded border-[var(--vbase-border)]" />
                </th>
                <th>Name</th>
                <th>Job title</th>
                <th>Company</th>
                <th>Email</th>
                <th>Email status</th>
                <th>Phone</th>
                <th>Phone status</th>
                <th>LinkedIn</th>
                <th>Location</th>
                <th>Industry</th>
                <th>Employee count</th>
                <th>Quality</th>
                <th>Last verified</th>
                <th className="w-10"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--vbase-border)]">
              {contacts.map((c) => (
                <tr key={c.id} className={selected.has(c.id) ? "bg-[var(--vbase-indigo)]/5" : ""}>
                  <td className="sticky left-10">
                    <input type="checkbox" checked={selected.has(c.id)} onChange={() => { const next = new Set(selected); next.has(c.id) ? next.delete(c.id) : next.add(c.id); setSelected(next); }} className="h-4 w-4 rounded border-[var(--vbase-border)]" />
                  </td>
                  <td>
                    <div className="flex items-center gap-2">
                      <div className="h-7 w-7 flex items-center justify-center rounded-md bg-[var(--vbase-bg-alt)] text-[var(--vbase-slate600)]"><IconUsers className="h-4 w-4" /></div>
                      <div className="min-w-0">
                        <p className="truncate max-w-[180px] font-medium text-[var(--vbase-slate900)]">{c.display_name || c.full_name || "—"}</p>
                      </div>
                    </div>
                  </td>
                  <td className="text-[var(--vbase-slate700)]">{c.job_title || <span className="text-[var(--vbase-slate400)]">—</span>}</td>
                  <td>
                    <div className="flex items-center gap-1.5">
                      {c.company ? <div className="h-6 w-6 flex items-center justify-center rounded border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] text-[6px]"><IconBuilding2 className="h-3 w-3 text-[var(--vbase-slate500)]" /></div> : <div className="h-6 w-6 flex items-center justify-center rounded border border-dashed border-[var(--vbase-border)] bg-transparent" />}
                      <span className="text-[var(--vbase-slate700)]">{c.company?.name || c.company_name || <span className="text-[var(--vbase-slate400)]">—</span>}</span>
                    </div>
                  </td>
                  <td className="text-[var(--vbase-slate700)]">{c.email ? <span className="flex items-center gap-1 text-[var(--vbase-slate800)]"><IconMail className="h-3 w-3 text-[var(--vbase-slate500)]" />{c.email}</span> : <span className="text-[var(--vbase-slate400)]">—</span>}</td>
                  <td><StatusBadge status={c.email_status} /></td>
                  <td className="text-[var(--vbase-slate700)]">{c.phone ? <span className="flex items-center gap-1 text-[var(--vbase-slate800)]"><IconPhone className="h-3 w-3 text-[var(--vbase-slate500)]" />{c.phone}</span> : <span className="text-[var(--vbase-slate400)]">—</span>}</td>
                  <td><StatusBadge status={c.phone_status} /></td>
                  <td>
                    {c.linkedin_url ? <a href={c.linkedin_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-[var(--vbase-indigo)] hover:underline text-xs"><IconLink className="h-3 w-3" />LinkedIn</a> : <span className="text-[var(--vbase-slate400)]">—</span>}
                  </td>
                  <td>
                    {c.city && <div className="text-[var(--vbase-slate800)]">{c.city}</div>}
                    {c.country && <div className="text-xs text-[var(--vbase-slate500)]">{c.country}</div>}
                  </td>
                  <td>{c.company?.industry || <span className="text-[var(--vbase-slate400)]">—</span>}</td>
                  <td>{c.company?.employee_count != null ? formatNumber(c.company.employee_count) : <span className="text-[var(--vbase-slate400)]">—</span>}</td>
                  <td><QualityBadge score={c.data_quality_score} /></td>
                  <td className="text-[var(--vbase-slate500)]">{c.last_verified ? new Date(c.last_verified).toLocaleDateString() : <span className="text-[var(--vbase-slate400)]">—</span>}</td>
                  <td className="relative">
                    <div className="flex h-full items-center">
                      <button className="flex h-8 w-8 items-center justify-center rounded-md text-[var(--vbase-slate500)] transition-colors hover:bg-[var(--vbase-bg-alt)] hover:text-[var(--vbase-slate700)]" title="Actions"><IconMoreHorizontal className="h-4 w-4" /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!contacts.length && (
          <div className="flex flex-col items-center justify-center gap-3 px-8 py-16 text-center text-sm text-[var(--vbase-slate500)]">
            <IconUsers className="h-8 w-8 text-[var(--vbase-slate300)]" />
            No contacts yet
          </div>
        )}
        <div className="border-t border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-4 py-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-[var(--vbase-slate500)]">{total} contacts</span>
            <div className="flex items-center gap-2">
              <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page <= 1} className="vbase-btn-ghost flex items-center gap-1"><IconRotateCcw className="h-4 w-4" /><span>Previous</span></button>
              <span className="text-sm text-[var(--vbase-slate500)]">{page} / {Math.max(1, Math.ceil(total / pageSize))}</span>
              <button onClick={() => setPage(Math.min(Math.ceil(total / pageSize), page + 1))} disabled={page >= Math.ceil(total / pageSize)} className="vbase-btn-ghost flex items-center gap-1"><span>Next</span><IconRotateCcw className="h-4 w-4 -scale-x-100" /></button>
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
      <div className="h-8 w-48 rounded-md bg-[var(--vbase-slate200)]" />
      <div className="h-4 w-96 rounded bg-[var(--vbase-slate200)]" />
    </div>
  );
}

function FiltersBar({ search, onSearch, filters, onFilters }: any) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="relative flex-1 max-w-xs">
        <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--vbase-slate400)]" />
        <input type="search" value={search} onChange={(e) => onSearch(e.target.value)} placeholder="Search contacts, emails, phones, companies…" className="vbase-input pl-9" />
      </div>
      <select value={filters.job_title || ""} onChange={(e) => onFilters({...filters, job_title: e.target.value})} className="vbase-select max-w-[160px]">
        <option value="">Job title</option>
        {["CTO", "CEO", "CFO", "HR Manager", "Founder", "VP Engineering", "Product Manager", "Other"].map(t => <option key={t} value={t}>{t}</option>)}
      </select>
      <select value={filters.email_status || ""} onChange={(e) => onFilters({...filters, email_status: e.target.value})} className="vbase-select max-w-[120px]">
        <option value="">Email status</option>
        {["Verified", "Pending", "Invalid", "Missing"].map(s => <option key={s} value={s}>{s}</option>)}
      </select>
      <button onClick={() => onFilters({})} className="vbase-btn-ghost flex items-center gap-1.5 text-sm"><IconX className="h-3.5 w-3.5" /> Clear</button>
    </div>
  );
}

function formatNumber(n: number) {
  if (n >= 1000000) return (n / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  return String(n);
}

function StatusBadge({ status }: { status?: string | null }) {
  if (!status) return <span className="text-[var(--vbase-slate400)]">—</span>;
  return <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${status.toLowerCase() === "verified" ? "bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]" : status.toLowerCase() === "pending" ? "bg-[var(--vbase-amber)]/10 text-[var(--vbase-amber)]" : status.toLowerCase() === "invalid" ? "bg-[var(--vbase-red)]/10 text-[var(--vbase-red)]" : "bg-[var(--vbase-slate100)] text-[var(--vbase-slate500)]"}`}>{status}</span>;
}

function QualityBadge({ score }: { score: number }) {
  return <div className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${score >= 70 ? "bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]" : score >= 40 ? "bg-[var(--vbase-amber)]/10 text-[var(--vbase-amber)]" : "bg-[var(--vbase-red)]/10 text-[var(--vbase-red)]"}`}>{score}</div>;
}

