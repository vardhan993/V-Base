import { Link, useNavigate } from "react-router-dom";
import { Contact } from "@/lib/types";
import { ContactEditor } from "@/components/crm";
import { IconChevronLeft } from "@/lib/icons";
import { toast } from "@/lib/store";

/** Create a contact from scratch — the same editor the detail page uses, in
 * create mode, so every column is reachable without going through Import. */
export function ContactNewPage() {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <Link to="/contacts" className="vbase-btn-ghost flex items-center gap-1.5 text-sm">
          <IconChevronLeft className="h-4 w-4" />
          Back to contacts
        </Link>
        <span className="ml-auto text-sm text-[var(--vbase-slate500)]">New contact</span>
      </div>

      <ContactEditor
        contact={null}
        company={null}
        onSaved={(created: Contact) => {
          toast("Contact created", "success");
          navigate(`/contacts/${created.id}`);
        }}
        onCancel={() => navigate("/contacts")}
      />
    </div>
  );
}
