import { Fragment, useState, useEffect, useCallback } from "react";
import { IconSearch, IconBuilding2, IconUsers } from "@/lib/icons";
import { api } from "@/lib/api";
import { ENTITY_LABELS, COMPANY_FIELDS, CONTACT_FIELDS, FieldDef } from "@/lib/fields";

export function AllRecordsPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const search = useCallback(async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await api.get<any>("/search/global", { params: { q: query, limit: 50 } });
      setResults(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    let cancelled = false;
    const t = setTimeout(() => {
      if (!cancelled) search();
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [search]);

  type SectionType = keyof typeof ENTITY_LABELS;

  function asSection(
    type: SectionType,
    items: any[],
    fields: FieldDef[]
  ): { type: SectionType; items: any[]; fields: FieldDef[] } {
    return { type, items, fields };
  }

  const sections = !results
    ? []
    : [
        asSection("company", results.companies || [], COMPANY_FIELDS),
        asSection("contact", results.contacts || [], CONTACT_FIELDS),
      ].filter((section) => section.items.length > 0);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">All Records</h1>
      <div className="relative max-w-3xl">
        <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--vbase-slate400)]" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search across contacts and companies, emails, phones, LinkedIn..."
          className="vbase-input pl-9 h-10"
        />
      </div>

      {loading && !results && (
        <div className="flex h-40 items-center justify-center">
          <div className="h-6 w-48 rounded bg-[var(--vbase-slate200)]" />
        </div>
      )}

      {sections.map((section) => (
        <div key={section.type} className="vbase-card overflow-hidden">
          <div className="border-b border-[var(--vbase-border)] px-4 py-3">
            <div className="flex items-center gap-2">
              {section.type === "company" ? (
                <IconBuilding2 className="h-4 w-4 text-[var(--vbase-slate500)]" />
              ) : (
                <IconUsers className="h-4 w-4 text-[var(--vbase-slate500)]" />
              )}
              <h3 className="font-semibold text-[var(--vbase-slate800)]">{ENTITY_LABELS[section.type]}</h3>
              <span className="text-xs text-[var(--vbase-slate500)]">
                {section.items.length} record{section.items.length === 1 ? "" : "s"}
              </span>
            </div>
          </div>

          <div className="overflow-x-auto">
            <div className="min-w-[640px]">
              <div className="grid grid-cols-[180px_minmax(0,1fr)] gap-2 border-b border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-4 py-2 text-left text-xs font-semibold text-[var(--vbase-slate600)] uppercase tracking-wider">
                <span>Field</span>
                <span>Value</span>
              </div>

              <div className="divide-y divide-[var(--vbase-border)]">
                {section.items.map((record) => (
                  <div key={`${section.type}-${record.id}`} className="px-4 py-3">
                    <div className="grid grid-cols-[180px_minmax(0,1fr)] gap-x-2 gap-y-1">
                      {section.fields.map((field) => (
                        <Fragment key={field.key}>
                          <span className="truncate whitespace-nowrap pt-0.5 text-xs font-medium text-[var(--vbase-slate500)]" title={field.label}>
                            {field.label}
                          </span>
                          <RecordCell record={record} field={field} />
                        </Fragment>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      ))}

      {!query && !results && (
        <div className="flex flex-col items-center gap-3 py-16 text-center text-sm text-[var(--vbase-slate500)]">
          <IconSearch className="h-8 w-8" />
          <p>Enter a search to find records across companies and contacts.</p>
        </div>
      )}
    </div>
  );
}

interface RecordCellProps {
  record: {
    id: unknown;
    fields?: Record<string, unknown>;
  } & Record<string, unknown>;
  field: FieldDef;
}

function RecordCell({ record, field }: RecordCellProps) {
  const value = record.fields?.[field.key] ?? record[field.key];

  if (value === null || value === undefined) {
    return <span className="text-sm text-[var(--vbase-slate400)]">—</span>;
  }

  if (Array.isArray(value)) {
    const text = value.join(", ");
    return (
      <span className="block truncate text-sm text-[var(--vbase-slate600)]" title={text}>
        {text}
      </span>
    );
  }

  if (typeof value === "number") {
    return <span className="text-sm text-[var(--vbase-slate800)]">{value}</span>;
  }

  if (typeof value === "boolean") {
    return value ? <span className="text-sm text-[var(--vbase-green)]">yes</span> : <span className="text-sm text-[var(--vbase-slate400)]">no</span>;
  }

  if (typeof value === "string" && (field.key === "linkedin_url" || value.startsWith("http"))) {
    return (
      <a
        href={value}
        target="_blank"
        rel="noreferrer"
        title={value}
        className="block truncate text-sm text-[var(--vbase-indigo)] hover:underline"
      >
        {value}
      </a>
    );
  }

  if (typeof value === "string") {
    return (
      <span className="block truncate text-sm text-[var(--vbase-slate800)]" title={value}>
        {value}
      </span>
    );
  }

  return <span className="block truncate text-sm text-[var(--vbase-slate800)]">{String(value)}</span>;
}
