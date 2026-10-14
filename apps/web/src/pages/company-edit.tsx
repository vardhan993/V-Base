import { useState, useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { Company } from "@/lib/types";
import { CompanyEditor } from "@/components/crm";
import { IconChevronLeft, IconArrowLeft } from "@/lib/icons";
import { toast } from "@/lib/store";

/** Full-record company editor, mirroring /contacts/:id/edit. */
export function CompanyEditPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [company, setCompany] = useState<Company | null>(null);
  const [loading, setLoading] = useState(true);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    if (!id || isNaN(Number(id))) {
      setMissing(true);
      setLoading(false);
      return;
    }
    let cancelled = false;
    const load = async () => {
      try {
        const data = await api.get<Company>(`/companies/${id}`);
        if (!cancelled) setCompany(data);
      } catch {
        if (!cancelled) setMissing(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading) {
    return (
      <div className="flex flex-col gap-3">
        <div className="h-8 w-48 rounded bg-[var(--vbase-slate200)]" />
        <div className="h-8 w-72 rounded bg-[var(--vbase-slate200)]" />
      </div>
    );
  }

  if (missing || !company) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center text-sm text-[var(--vbase-slate500)]">
        <p>Company could not be loaded.</p>
        <Link to="/companies" className="vbase-btn-secondary flex items-center gap-1.5 text-sm">
          <IconArrowLeft className="h-4 w-4" />
          Back to companies
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <Link to={`/companies/${company.id}`} className="vbase-btn-ghost flex items-center gap-1.5 text-sm">
          <IconChevronLeft className="h-4 w-4" />
          Back to company
        </Link>
        <span className="ml-auto text-sm text-[var(--vbase-slate500)]">Editing full record</span>
      </div>

      <CompanyEditor
        company={company}
        onSaved={(updated) => {
          setCompany(updated);
          toast("Company updated", "success");
        }}
        onDelete={() => navigate("/companies")}
      />
    </div>
  );
}
