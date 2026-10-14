import { useParams, Link, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Contact, Company } from "@/lib/types";
import { toast } from "@/lib/store";
import { ContactEditor } from "@/components/crm";
import { IconChevronLeft, IconArrowLeft } from "@/lib/icons";

export function ContactEditPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [contact, setContact] = useState<Contact | null>(null);
  const [company, setCompany] = useState<{ id: number; name: string } | null>(null);
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
        const c = await api.get<Contact>(`/contacts/${id}`);
        if (cancelled) return;
        setContact(c);
        // The contact payload does not embed the company, so resolve the link
        // separately. A missing company is normal (the record is unlinked).
        const co = await api.get<Company | null>(`/contacts/${id}/company`).catch(() => null);
        if (!cancelled) setCompany(co ? { id: co.id, name: co.name } : null);
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

  if (missing || !contact) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center text-sm text-[var(--vbase-slate500)]">
        <p>Contact could not be loaded.</p>
        <Link to="/contacts" className="vbase-btn-secondary flex items-center gap-1.5 text-sm">
          <IconArrowLeft className="h-4 w-4" />
          Back to contacts
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <Link to={`/contacts/${contact.id}`} className="vbase-btn-ghost flex items-center gap-1.5 text-sm">
          <IconChevronLeft className="h-4 w-4" />
          Back to contact
        </Link>
        <span className="ml-auto text-sm text-[var(--vbase-slate500)]">Editing full record</span>
      </div>

      <ContactEditor
        contact={contact}
        company={company}
        onSaved={(updated) => {
          setContact(updated);
          toast("Contact updated", "success");
        }}
        onDelete={() => navigate("/contacts")}
      />
    </div>
  );
}
