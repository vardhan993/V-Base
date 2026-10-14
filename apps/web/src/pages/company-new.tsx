import { Link, useNavigate } from "react-router-dom";
import { Company } from "@/lib/types";
import { CompanyEditor } from "@/components/crm";
import { IconChevronLeft } from "@/lib/icons";
import { toast } from "@/lib/store";

/** Create a company/account from scratch. */
export function CompanyNewPage() {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <Link to="/companies" className="vbase-btn-ghost flex items-center gap-1.5 text-sm">
          <IconChevronLeft className="h-4 w-4" />
          Back to companies
        </Link>
        <span className="ml-auto text-sm text-[var(--vbase-slate500)]">New company</span>
      </div>

      <CompanyEditor
        company={null}
        onSaved={(created: Company) => {
          toast("Company created", "success");
          navigate(`/companies/${created.id}`);
        }}
        onCancel={() => navigate("/companies")}
      />
    </div>
  );
}
