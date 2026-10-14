export interface User {
  id: number;
  email: string;
  username: string;
  full_name?: string | null;
  is_active: boolean;
  is_superuser: boolean;
  preferences: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

export interface Company {
  id: number;
  name: string;
  website?: string | null;
  domain?: string | null;
  linkedin_url?: string | null;
  industry?: string | null;
  sub_industry?: string | null;
  employee_count?: number | null;
  company_size?: string | null;
  country?: string | null;
  state?: string | null;
  city?: string | null;
  headquarters?: string | null;
  founded_year?: number | null;
  technologies: string[];
  funding_stage?: string | null;
  company_status?: string | null;
  source?: string | null;
  notes?: string | null;
  data_quality_score: number;
  is_archived: boolean;
  last_verified?: string | null;
  created_by_id?: number | null;
  created_at?: string;
  updated_at?: string;
  contact_count?: number;
  tag_names?: string[];
}

export interface Contact {
  id: number;
  first_name?: string | null;
  last_name?: string | null;
  full_name?: string | null;
  job_title?: string | null;
  department?: string | null;
  seniority?: string | null;
  email?: string | null;
  email_status?: string | null;
  phone?: string | null;
  phone_status?: string | null;
  stage?: string;
  linkedin_url?: string | null;
  company_name?: string | null;
  city?: string | null;
  country?: string | null;
  skills: string[];
  employment_history: any[];
  source?: string | null;
  notes?: string | null;
  data_quality_score: number;
  is_archived: boolean;
  last_verified?: string | null;
  company_id?: number | null;
  created_by_id?: number | null;
  created_at?: string;
  updated_at?: string;
  company?: Company | null;
  tag_names?: string[];
  display_name?: string;
  name?: string;
}

export interface ScoreRule {
  key: string;
  label: string;
  kind: string;
  weight: number;
  points: number;
  earned: boolean;
  detail: string;
}

/** A prospect tracked from discovery through qualification. Mirrors
 * ``LeadResponse`` in backend/src/nexus/schemas/lead.py. */
export interface Lead {
  id: number;
  first_name?: string | null;
  last_name?: string | null;
  full_name?: string | null;
  job_title?: string | null;
  department?: string | null;
  seniority?: string | null;
  email?: string | null;
  email_status?: string | null;
  phone?: string | null;
  phone_status?: string | null;
  linkedin_url?: string | null;
  website?: string | null;
  company_name?: string | null;
  company_domain?: string | null;
  industry?: string | null;
  employee_count?: number | null;
  company_size?: string | null;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  lead_source?: string | null;
  campaign?: string | null;
  lifecycle_stage: string;
  lead_status: string;
  priority: string;
  lead_score: number;
  score_breakdown: ScoreRule[];
  score_updated_at?: string | null;
  owner_id?: number | null;
  company_id?: number | null;
  next_follow_up_at?: string | null;
  consent_status?: string | null;
  do_not_contact: boolean;
  disqualified_reason?: string | null;
  notes?: string | null;
  converted_contact_id?: number | null;
  converted_company_id?: number | null;
  converted_at?: string | null;
  data_quality_score: number;
  is_archived: boolean;
  last_verified?: string | null;
  created_by_id?: number | null;
  created_at?: string;
  updated_at?: string;
  tag_names?: string[];
  display_name?: string;
  fit_score: number;
  engagement_score: number;
  score_summary: string;
}

/** Result of converting a lead. Mirrors ``LeadConvertResponse``. */
export interface LeadConversion {
  lead: Lead;
  contact: Contact;
  company: Company | null;
  created_contact: boolean;
  created_company: boolean;
}

export interface Tag {
  id: number;
  name: string;
  color?: string | null;
  kind?: string | null;
}

export interface ContactList {
  id: number;
  name: string;
  description?: string | null;
  kind?: string | null;
  contact_count?: number;
}

export interface SavedSearch {
  id: number;
  name: string;
  query?: string | null;
  scope?: string | null;
  created_at?: string;
}

export interface ImportJob {
  id: number;
  filename: string;
  file_size_bytes?: number | null;
  status: string;
  rows_total?: number | null;
  rows_processed?: number | null;
  rows_added?: number | null;
  rows_updated?: number | null;
  rows_duplicate?: number | null;
  rows_invalid?: number | null;
  rows_skipped?: number | null;
  created_at?: string;
}

export interface ActivityLogEntry {
  id: number;
  user_id?: number | null;
  action: string;
  entity_type?: string | null;
  entity_id?: number | null;
  description?: string | null;
  metadata: Record<string, any>;
  ip_address?: string | null;
  user_agent?: string | null;
  created_at?: string;
}

export interface DashboardMetrics {
  companies: number;
  contacts: number;
  emails_available: number;
  phones_available: number;
  linkedin_profiles: number;
  verified_emails: number;
  records_needing_review: number;
}

export interface QualitySummary {
  contacts: {
    total: number;
    with_email: number;
    with_phone: number;
    with_linkedin: number;
    with_company: number;
    invalid_email: number;
    phone_missing_country_code: number;
    missing_job_title: number;
    missing_phone: number;
    missing_linkedin: number;
    stale: number;
  };
  companies: {
    total: number;
    missing_domain: number;
    missing_website: number;
    missing_linkedin: number;
    stale: number;
  };
}

export type ThemeMode = "light" | "dark" | "system";
export type ToastType = "success" | "error" | "info";

/** One email in a sequence. ``delay_days`` is the wait before this step. */
export interface SequenceStep {
  id?: number;
  position: number;
  delay_days: number;
  subject: string;
  body: string;
}

export interface EmailSequence {
  id: number;
  name: string;
  description?: string | null;
  is_active: boolean;
  steps: SequenceStep[];
  step_count: number;
  active_enrollments: number;
  completed_enrollments: number;
  failed_enrollments: number;
  emails_sent: number;
  created_at?: string | null;
}

/** Where one contact stands in one sequence. */
export interface SequenceEnrollment {
  id: number;
  sequence_id: number;
  sequence_name?: string | null;
  contact_id: number;
  contact_name?: string | null;
  contact_email?: string | null;
  status: "active" | "paused" | "completed" | "cancelled" | "failed";
  current_step: number;
  next_send_at?: string | null;
  last_sent_at?: string | null;
  last_error?: string | null;
  created_at?: string | null;
}
