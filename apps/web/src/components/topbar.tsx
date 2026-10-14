import { useState, useRef, useEffect, useCallback, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuthStore, useThemeStore, useCommandPaletteStore } from "@/lib/store";
import {
  IconSearch,
  IconPlus,
  IconFileSpreadsheet,
  IconCommand,
  IconUser,
  IconLogout,
  IconSettings,
  IconUsers,
  IconBuilding2,
  IconSparkle,
  IconBell,
  IconChevronDown,
  IconLoader2,
} from "@/lib/icons";

interface TaskSummary {
  open: number;
  overdue: number;
  due_soon: number;
}

interface FollowUp {
  id: number;
  title: string;
  due_at?: string | null;
  contact_id?: number | null;
  contact_name?: string | null;
}

export function Topbar() {
  const { user, logout } = useAuthStore();
  const { setOpen: setPaletteOpen } = useCommandPaletteStore();
  const [search, setSearch] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [setPaletteOpen]);

  // Submitting hands the query to the Contacts list, which already understands
  // every filter the CRM exposes. Typing must not navigate — that made the box
  // unusable, as each keystroke replaced the route mid-word.
  const submitSearch = useCallback(
    (e: FormEvent) => {
      e.preventDefault();
      const q = search.trim();
      if (!q) return;
      navigate(`/contacts?search=${encodeURIComponent(q)}`);
    },
    [navigate, search],
  );

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-4 border-b border-[var(--vbase-border)] bg-[var(--vbase-bg)]/95 backdrop-blur supports-[backdrop-filter]:bg-[var(--vbase-bg)]/70 px-4">
      <form onSubmit={submitSearch} className="flex flex-1 items-center gap-3">
        <div className="relative flex w-full max-w-md items-center rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg)] py-1.5 pl-3 pr-9 shadow-sm">
          <IconSearch className="ml-2 h-4 w-4 text-[var(--vbase-slate500)]" />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search contacts, companies, emails, phones, LinkedIn..."
            aria-label="Search contacts"
            className="h-8 w-full bg-transparent px-2 text-sm text-[var(--vbase-slate800)] placeholder:text-[var(--vbase-slate500)] focus:outline-none"
          />
          <kbd className="absolute right-2 hidden items-center gap-0.5 rounded border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--vbase-slate500)] tracking-tight sm:flex">
            <span className="i-svg">⌘</span>K
          </kbd>
        </div>
      </form>

      <div className="flex items-center gap-1.5">
        <Link
          to="/import"
          className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium text-[var(--vbase-slate700)] transition-colors hover:bg-[var(--vbase-muted-bg)] hover:text-[var(--vbase-slate900)]"
        >
          <IconFileSpreadsheet className="h-4 w-4" />
          <span className="hidden sm:inline">Import</span>
        </Link>

        <QuickAddMenu />

        <div className="h-5 w-px bg-[var(--vbase-border)]" />

        <FollowUpsBell />

        <div className="ml-auto flex items-center gap-2">
          <button
            className="flex h-8 w-8 items-center justify-center rounded-full text-sm text-[var(--vbase-slate600)] transition-colors hover:bg-[var(--vbase-muted-bg)] hover:text-[var(--vbase-slate800)]"
            title="Command palette (Ctrl+K)"
            onClick={() => setPaletteOpen(true)}
          >
            <IconCommand className="h-4 w-4" />
          </button>

          <div className="flex items-center gap-2 rounded-full bg-[var(--vbase-muted-bg)] px-3 py-1.5 text-sm">
            <IconUser className="h-4 w-4 text-[var(--vbase-slate500)]" />
            <span className="font-medium text-[var(--vbase-slate800)]">{user?.full_name || user?.email || "User"}</span>
            <button
              onClick={logout}
              aria-label="Sign out"
              className="ml-1 rounded-full p-1 text-[var(--vbase-slate500)] transition-colors hover:bg-[var(--vbase-border)] hover:text-[var(--vbase-slate700)]"
            >
              <IconLogout className="h-3.5 w-3.5" />
            </button>
            <Link
              to="/settings"
              aria-label="Settings"
              className="rounded-full p-1 text-[var(--vbase-slate500)] transition-colors hover:bg-[var(--vbase-border)] hover:text-[var(--vbase-slate700)]"
            >
              <IconSettings className="h-3.5 w-3.5" />
            </Link>
            <ThemeToggle />
          </div>
        </div>
      </div>
    </header>
  );
}

/** Closes a popover on an outside click or Escape. */
function useDismiss(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) close();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);
  return ref;
}

const QUICK_ADD_ITEMS = [
  { to: "/contacts/new", label: "New contact", hint: "A person with email, phone and company", icon: IconUsers },
  { to: "/companies/new", label: "New company", hint: "An account with domain and industry", icon: IconBuilding2 },
  { to: "/leads/new", label: "New lead", hint: "Score and qualify before converting", icon: IconSparkle },
];

function QuickAddMenu() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const ref = useDismiss(open, useCallback(() => setOpen(false), []));

  const go = (to: string) => {
    setOpen(false);
    navigate(to);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium text-[var(--vbase-slate700)] transition-colors hover:bg-[var(--vbase-muted-bg)] hover:text-[var(--vbase-slate900)]"
      >
        <IconPlus className="h-4 w-4" />
        <span className="hidden sm:inline">Quick Add</span>
        <IconChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-10 z-50 min-w-[260px] rounded-lg border border-[var(--vbase-border)] bg-[var(--vbase-bg)] py-1.5 shadow-[0_10px_30px_-8px_rgba(0,0,0,0.25)]"
        >
          {QUICK_ADD_ITEMS.map((item) => (
            <button
              key={item.to}
              type="button"
              role="menuitem"
              onClick={() => go(item.to)}
              className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left transition-colors hover:bg-[var(--vbase-muted-bg)]"
            >
              <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]">
                <item.icon className="h-3.5 w-3.5" />
              </span>
              <span className="flex min-w-0 flex-col">
                <span className="text-sm font-medium text-[var(--vbase-slate800)]">{item.label}</span>
                <span className="truncate text-xs text-[var(--vbase-slate500)]">{item.hint}</span>
              </span>
            </button>
          ))}
          <div className="my-1 border-t border-[var(--vbase-border)]" />
          <button
            type="button"
            role="menuitem"
            onClick={() => go("/import")}
            className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left transition-colors hover:bg-[var(--vbase-muted-bg)]"
          >
            <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]">
              <IconFileSpreadsheet className="h-3.5 w-3.5" />
            </span>
            <span className="flex min-w-0 flex-col">
              <span className="text-sm font-medium text-[var(--vbase-slate800)]">Import a spreadsheet</span>
              <span className="truncate text-xs text-[var(--vbase-slate500)]">CSV or Excel, with column mapping</span>
            </span>
          </button>
        </div>
      )}
    </div>
  );
}

/** Follow-ups popover: real overdue/due-soon counts from the tasks API. */
function FollowUpsBell() {
  const [open, setOpen] = useState(false);
  const [summary, setSummary] = useState<TaskSummary | null>(null);
  const [overdue, setOverdue] = useState<FollowUp[]>([]);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const ref = useDismiss(open, useCallback(() => setOpen(false), []));

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const [s, list] = await Promise.all([
          api.get<TaskSummary>("/tasks/summary"),
          api.get<{ items: FollowUp[] }>("/tasks", { params: { overdue: true, page_size: 5 } }),
        ]);
        if (!cancelled) {
          setSummary(s);
          setOverdue(list.items);
        }
      } catch {
        /* the bell is informational — keep whatever we already had */
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    // Refresh periodically so a session left open still shows current work.
    const timer = window.setInterval(load, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const overdueCount = summary?.overdue ?? 0;
  const tone = overdueCount > 0 ? "text-[var(--vbase-red)]" : "text-[var(--vbase-slate600)]";

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        title={
          overdueCount > 0
            ? `${overdueCount} overdue follow-up${overdueCount === 1 ? "" : "s"}`
            : "No overdue follow-ups"
        }
        className={`relative flex items-center gap-2 rounded-full px-3 py-1.5 text-sm transition-colors hover:bg-[var(--vbase-muted-bg)] ${tone}`}
      >
        {loading && !summary ? (
          <IconLoader2 className="h-4 w-4 animate-spin" />
        ) : (
          <IconBell className="h-4 w-4" />
        )}
        <span className="text-xs font-medium">{overdueCount}</span>
        {overdueCount > 0 && (
          <span className="absolute right-2 top-1 flex h-2 w-2 rounded-full bg-[var(--vbase-red)]" />
        )}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-10 z-50 w-[320px] rounded-lg border border-[var(--vbase-border)] bg-[var(--vbase-bg)] p-3 shadow-[0_10px_30px_-8px_rgba(0,0,0,0.25)]"
        >
          <div className="mb-2 grid grid-cols-3 gap-2 text-center">
            <Stat label="Open" value={summary?.open ?? 0} />
            <Stat label="Overdue" value={overdueCount} tone="red" />
            <Stat label="Due soon" value={summary?.due_soon ?? 0} tone="amber" />
          </div>

          <p className="mt-3 mb-1 text-xs font-semibold uppercase tracking-wider text-[var(--vbase-slate500)]">
            Overdue
          </p>
          {overdue.length ? (
            <ul className="space-y-1">
              {overdue.map((t) => (
                <li key={t.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setOpen(false);
                      navigate(t.contact_id ? `/contacts/${t.contact_id}` : "/tasks");
                    }}
                    className="flex w-full flex-col rounded-md px-2 py-1.5 text-left transition-colors hover:bg-[var(--vbase-muted-bg)]"
                  >
                    <span className="truncate text-sm text-[var(--vbase-slate800)]" title={t.title}>
                      {t.title}
                    </span>
                    <span className="truncate text-xs text-[var(--vbase-slate500)]">
                      {t.contact_name || "Unassigned"}
                      {t.due_at ? ` · due ${new Date(t.due_at).toLocaleDateString()}` : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-2 py-1.5 text-sm text-[var(--vbase-slate500)]">Nothing is overdue. Nice.</p>
          )}

          <button
            type="button"
            onClick={() => {
              setOpen(false);
              navigate("/tasks");
            }}
            className="mt-2 w-full rounded-md border border-[var(--vbase-border)] py-1.5 text-sm font-medium text-[var(--vbase-slate700)] transition-colors hover:border-[var(--vbase-indigo)] hover:text-[var(--vbase-indigo)]"
          >
            Open all follow-ups
          </button>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: "red" | "amber" }) {
  const color = tone === "red" ? "text-[var(--vbase-red)]" : tone === "amber" ? "text-[var(--vbase-amber)]" : "text-[var(--vbase-slate900)]";
  return (
    <div className="rounded-md bg-[var(--vbase-bg-alt)] px-2 py-1.5">
      <p className={`text-lg font-semibold ${color}`}>{value}</p>
      <p className="text-[10px] uppercase tracking-wider text-[var(--vbase-slate500)]">{label}</p>
    </div>
  );
}

function ThemeToggle() {
  const { mode, setMode } = useThemeStore();
  const next = (mode: string) => {
    if (mode === "light") return "dark";
    if (mode === "dark") return "system";
    return "light";
  };

  return (
    <button
      onClick={() => setMode(next(mode) as any)}
      className="flex h-8 w-8 items-center justify-center rounded-full text-[var(--vbase-slate500)] transition-colors hover:bg-[var(--vbase-border)] hover:text-[var(--vbase-slate700)]"
      title={`Theme: ${mode}`}
    >
      <ThemeIcon mode={mode} />
    </button>
  );
}

function ThemeIcon({ mode }: { mode: string }) {
  if (mode === "light") {
    return <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" /></svg>;
  }
  if (mode === "dark") {
    return <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></svg>;
  }
  return <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2" /><path d="M8 21h8" /><path d="M12 17v4" /></svg>;
}
