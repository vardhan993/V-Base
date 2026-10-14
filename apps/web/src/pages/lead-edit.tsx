import { useState, useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { Lead } from "@/lib/types";
import { LeadEditor } from "@/components/crm";
import { IconChevronLeft, IconArrowLeft } from "@/lib/icons";
import { toast } from "@/lib/store";

/** Full-record lead editor, mirroring /contacts/:id/edit. */
export function LeadEditPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [lead, setLead] = useState<Lead | null>(null);
  const [loading, setLoading] = useState(true);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    if (!id || isNaN(Number(id))) {
      setMissing(true);
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const data = await api.get<Lead>(`/leads/${id}`);
        if (!cancelled) setLead(data);
      } catch {
        if (!cancelled) setMissing(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
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

  if (missing || !lead) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center text-sm text-[var(--vbase-slate500)]">
        <p>Lead could not be loaded.</p>
        <Link to="/leads" className="vbase-btn-secondary flex items-center gap-1.5 text-sm">
          <IconArrowLeft className="h-4 w-4" />
          Back to leads
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <Link to={`/leads/${lead.id}`} className="vbase-btn-ghost flex items-center gap-1.5 text-sm">
          <IconChevronLeft className="h-4 w-4" />
          Back to lead
        </Link>
        <span className="ml-auto text-sm text-[var(--vbase-slate500)]">Editing full record</span>
      </div>

      <LeadEditor
        lead={lead}
        onSaved={(updated) => {
          setLead(updated);
          toast("Lead updated", "success");
        }}
        onDelete={() => navigate("/leads")}
      />
    </div>
  );
}
