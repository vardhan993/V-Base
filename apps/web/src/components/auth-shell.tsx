import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  IconBuilding2,
  IconUsers,
  IconSearch,
  IconDatabase,
} from "@/lib/icons";

const FEATURES = [
  {
    icon: IconBuilding2,
    title: "Companies & contacts",
    text: "Import spreadsheets, clean duplicates and segment everything in one base.",
  },
  {
    icon: IconSearch,
    title: "Search that finds anything",
    text: "Fuzzy matching, full-text search and a Ctrl-K palette over every record.",
  },
  {
    icon: IconUsers,
    title: "Outreach built in",
    text: "Follow-up tasks, email sequences and delivery tracking per contact.",
  },
  {
    icon: IconDatabase,
    title: "Your data stays yours",
    text: "PostgreSQL you control, one-click backups, no vendor lock-in.",
  },
];

export function AuthShell({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen bg-[var(--vbase-bg)]">
      {/* Brand panel — hidden on small screens so the form gets the space. */}
      <aside className="vbase-auth-hero hidden lg:flex w-[44%] max-w-[640px] flex-col justify-between p-10 xl:p-14">
        <div className="relative z-10">
          <Link to="/login" className="inline-flex items-center gap-3">
            <span
              className="flex h-10 w-10 items-center justify-center rounded-xl text-white shadow-[0_0_20px_-4px_rgba(99,102,241,0.9)]"
              style={{ backgroundImage: "linear-gradient(135deg, var(--vbase-brand-a), var(--vbase-brand-b))" }}
            >
              <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 4h3v7H4z" />
                <path d="M9 4h3v4H9z" />
                <path d="M9 10h3v2h-3z" />
              </svg>
            </span>
            <span className="flex flex-col leading-tight">
              <span className="text-lg font-semibold tracking-tight">V-Base</span>
              <span className="text-[10px] font-medium uppercase tracking-[0.16em] text-indigo-200/80">
                Business intelligence
              </span>
            </span>
          </Link>
        </div>

        <div className="relative z-10 max-w-md">
          <h2 className="text-2xl font-semibold leading-snug">
            Your business data.
            <br />
            One powerful base.
          </h2>
          <ul className="mt-8 space-y-5">
            {FEATURES.map((f) => (
              <li key={f.title} className="vbase-auth-feature">
                <span className="vbase-auth-feature-icon">
                  <f.icon className="h-4 w-4" />
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold text-white">{f.title}</span>
                  <span className="block text-[13px] leading-relaxed text-indigo-100/70">{f.text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative z-10 text-xs text-indigo-100/50">
          Free tier · PostgreSQL-backed · local-first philosophy
        </p>
      </aside>

      {/* Form panel */}
      <main className="relative flex flex-1 flex-col items-center justify-center px-4 py-10">
        {/* Compact brand row for small screens where the hero is hidden. */}
        <div className="mb-8 flex items-center gap-2.5 lg:hidden">
          <span
            className="flex h-9 w-9 items-center justify-center rounded-lg text-white"
            style={{ backgroundImage: "linear-gradient(135deg, var(--vbase-brand-a), var(--vbase-brand-b))" }}
          >
            <svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 4h3v7H4z" />
              <path d="M9 4h3v4H9z" />
              <path d="M9 10h3v2h-3z" />
            </svg>
          </span>
          <span className="text-base font-semibold tracking-tight text-[var(--vbase-slate900)]">V-Base</span>
        </div>

        <div className="w-full max-w-[420px]">
          <div className="vbase-auth-card p-8">
            <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">{title}</h1>
            <p className="mt-1 text-sm text-[var(--vbase-slate500)]">{subtitle}</p>
            <div className="mt-6">{children}</div>
          </div>

          <p className="mt-6 text-center text-xs text-[var(--vbase-slate500)]">
            Protected by Argon2 password hashing and server-side sessions.
          </p>
        </div>
      </main>
    </div>
  );
}
