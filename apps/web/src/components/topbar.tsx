import { useState, useRef, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { useAuthStore, useThemeStore, useCommandPaletteStore } from "@/lib/store";
import { IconSearch, IconPlus, IconFileSpreadsheet, IconCommand, IconUser, IconLogout, IconSettings } from "@/lib/icons";

export function Topbar() {
  const { user, logout } = useAuthStore();
  const { setOpen: setPaletteOpen } = useCommandPaletteStore();
  const [search, setSearch] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

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

  const handleSearch = useCallback((value: string) => {
    setSearch(value);
    if (value.trim().length >= 2) {
      window.location.hash = `#/search?q=${encodeURIComponent(value.trim())}`;
    }
  }, []);

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-4 border-b border-[var(--vbase-border)] bg-[var(--vbase-bg)]/95 backdrop-blur supports-[backdrop-filter]:bg-[var(--vbase-bg)]/70 px-4">
      <div className="flex flex-1 items-center gap-3">
        <div className="relative flex w-full max-w-md items-center rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg)] py-1.5 pl-3 pr-9 shadow-sm">
          <IconSearch className="ml-2 h-4 w-4 text-[var(--vbase-slate500)]" />
          <input
            ref={inputRef}
            type="search"
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            onFocus={() => setPaletteOpen(true)}
            placeholder="Search across contacts, companies, emails, phones, LinkedIn..."
            className="h-8 w-full bg-transparent px-2 text-sm text-[var(--vbase-slate800)] placeholder:text-[var(--vbase-slate500)] focus:outline-none"
          />
          <kbd className="absolute right-2 hidden items-center gap-0.5 rounded border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--vbase-slate500)] tracking-tight sm:flex">
            <span className="i-svg">⌘</span>K
          </kbd>
        </div>
      </div>

      <div className="flex items-center gap-1.5">
        <Link to="/import" className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium text-[var(--vbase-slate700)] transition-colors hover:bg-[var(--vbase-muted-bg)] hover:text-[var(--vbase-slate900)]">
          <IconFileSpreadsheet className="h-4 w-4" />
          <span className="hidden sm:inline">Import</span>
        </Link>
        <button className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium text-[var(--vbase-slate700)] transition-colors hover:bg-[var(--vbase-muted-bg)] hover:text-[var(--vbase-slate900)]">
          <IconPlus className="h-4 w-4" />
          <span className="hidden sm:inline">Quick Add</span>
        </button>

        <div className="h-5 w-px bg-[var(--vbase-border)]" />

        <button className="relative flex items-center gap-2 rounded-full px-3 py-1.5 text-sm text-[var(--vbase-slate600)] transition-colors hover:bg-[var(--vbase-muted-bg)] hover:text-[var(--vbase-slate800)]">
          <span className="flex h-2 w-2 rounded-full bg-[var(--vbase-green)]" />
          <span className="text-xs font-medium">3</span>
        </button>

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
            <button onClick={logout} className="ml-1 rounded-full p-1 text-[var(--vbase-slate500)] transition-colors hover:bg-[var(--vbase-border)] hover:text-[var(--vbase-slate700)]">
              <IconLogout className="h-3.5 w-3.5" />
            </button>
            <Link to="/settings" className="rounded-full p-1 text-[var(--vbase-slate500)] transition-colors hover:bg-[var(--vbase-border)] hover:text-[var(--vbase-slate700)]">
              <IconSettings className="h-3.5 w-3.5" />
            </Link>
            <ThemeToggle />
          </div>
        </div>
      </div>
    </header>
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
