/** Canonical field definitions for the record grids (companies + contacts).

Every column label on the "All Records" page now comes from this module, so a
company field (for example "LinkedIn (company page)") and a contact field
(for example "LinkedIn") are declared separately. That is the only place both
can appear, and it is what keeps one set of names from being jumbled on top
of the other.
*/

export interface FieldDef {
  key: string;
  label: string;
  type?: "text" | "number" | "url" | "list";
}

/** Human-facing section label, not a field name. */
export const ENTITY_LABELS = {
  company: "Companies",
  contact: "Contacts",
} as const;

/** Company fields, in display order. */
export const COMPANY_FIELDS: FieldDef[] = [
  { key: "name", label: "Name" },
  { key: "domain", label: "Domain" },
  { key: "website", label: "Website" },
  { key: "industry", label: "Industry" },
  { key: "headcount", label: "Headcount" },
  { key: "size", label: "Company size" },
  { key: "city", label: "City" },
  { key: "country", label: "Country" },
  { key: "linkedin_url", label: "LinkedIn (company page)" },
  { key: "technologies", label: "Technologies" },
];

/** Contact fields, in display order. */
export const CONTACT_FIELDS: FieldDef[] = [
  { key: "first_name", label: "First name" },
  { key: "last_name", label: "Last name" },
  { key: "full_name", label: "Full name" },
  { key: "job_title", label: "Job title" },
  { key: "department", label: "Department" },
  { key: "seniority", label: "Seniority" },
  { key: "email", label: "Email" },
  { key: "phone", label: "Phone" },
  { key: "linkedin_url", label: "LinkedIn" },
  { key: "company_name", label: "Company" },
];
