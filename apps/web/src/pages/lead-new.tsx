import { Link, useNavigate } from "react-router-dom";
import { Lead } from "@/lib/types";
import { LeadEditor } from "@/components/crm";
import { IconChevronLeft } from "@/lib/icons";
import { toast } from "@/lib/store";

/** Create a lead from scratch — the same editor the detail page uses. */
export function LeadNewPage() {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <Link to="/leads" className="vbase-btn-ghost flex items-center gap-1.5 text-sm">
          <IconChevronLeft className="h-4 w-4" />
          Back to leads
        </Link>
        <span className="ml-auto text-sm text-[var(--vbase-slate500)]">New lead</span>
      </div>

      <LeadEditor
        lead={null}
        onSaved={(created: Lead) => {
          toast("Lead created", "success");
          navigate(`/leads/${created.id}`);
        }}
        onCancel={() => navigate("/leads")}
      />
    </div>
  );
}
