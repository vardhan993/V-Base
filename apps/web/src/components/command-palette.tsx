import { useEffect, useRef, useCallback, useState, useMemo } from "react";
import { } from "react-router-dom";
import { useCommandPaletteStore, useAuthStore } from "@/lib/store";
import { } from "@/lib/api";
import { IconCommand, IconUsers, IconBuilding2, IconFileSpreadsheet, IconHash, IconActivity, IconSettings, IconX } from "@/lib/icons";

interface Command {
  id: string;
  label: string;
  href: string;
  shortcut?: string;
  icon: any;
  section?: string;
}

const COMMANDS: Command[] = [
  { id: "dashboard", label: "Go to Dashboard", href: "/dashboard", icon: IconActivity, shortcut: "d", section: "Navigation" },
  { id: "pipeline", label: "Go to Pipeline", href: "/pipeline", icon: IconActivity, shortcut: "g p", section: "Navigation" },
  { id: "tasks", label: "Go to Follow-ups", href: "/tasks", icon: IconActivity, shortcut: "g t", section: "Navigation" },
  { id: "companies", label: "Go to Companies", href: "/companies", icon: IconBuilding2, shortcut: "g c", section: "Navigation" },
  { id: "contacts", label: "Go to Contacts", href: "/contacts", icon: IconUsers, shortcut: "g o", section: "Navigation" },
  { id: "lists", label: "Go to Lists", href: "/lists", icon: IconHash, shortcut: "g l", section: "Navigation" },
  { id: "saved-views", label: "Go to Saved Views", href: "/saved-views", icon: IconUsers, shortcut: "", section: "Navigation" },
  { id: "custom-fields", label: "Go to Custom Fields", href: "/custom-fields", icon: IconHash, shortcut: "", section: "Navigation" },
  { id: "backup", label: "Open Backup & Restore", href: "/backup", icon: IconSettings, shortcut: "", section: "Navigation" },
  { id: "import", label: "Open Import Center", href: "/import", icon: IconFileSpreadsheet, shortcut: "i", section: "Import" },
  { id: "analytics", label: "Go to Analytics", href: "/analytics", icon: IconActivity, shortcut: "a", section: "Navigation" },
  { id: "settings", label: "Open Settings", href: "/settings", icon: IconSettings, shortcut: ",", section: "Navigation" },
  { id: "search-contacts", label: "Search Contacts", href: "/contacts?search=", icon: IconUsers, shortcut: "", section: "Actions" },
  { id: "search-companies", label: "Search Companies", href: "/companies?search=", icon: IconBuilding2, shortcut: "", section: "Actions" },
];

export function CommandPalette() {
  const { open, setOpen, input, setInput } = useCommandPaletteStore();
  const { logout } = useAuthStore();
  const [results, setResults] = useState<Command[]>(COMMANDS);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      setInput("");
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open, setInput]);

  useEffect(() => {
    const q = input.trim().toLowerCase();
    let filtered = COMMANDS;
    if (q) {
      filtered = COMMANDS.filter((c) => c.label.toLowerCase().includes(q) || c.id.includes(q));
    }
    setResults(filtered);
    setSelectedIndex(0);
  }, [input]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    const items = results;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((i) => (i + 1) % items.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((i) => (i - 1 + items.length) % items.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const item = items[selectedIndex];
      if (item) {
        if (item.id === "search-contacts" || item.id === "search-companies") {
          const q = input.trim();
          if (q) {
            window.location.hash = `${item.href}${encodeURIComponent(q)}`;
            setOpen(false);
          }
        } else if (item.id === "logout") {
          logout();
          setOpen(false);
        } else {
          window.location.hash = item.href;
          setOpen(false);
        }
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    }
  }, [results, selectedIndex, input, setOpen, logout]);

  const sectionHeader = useMemo(() => {
    const sections: Record<string, Command[]> = {};
    results.forEach((cmd) => {
      if (!sections[cmd.section!]) sections[cmd.section!] = [];
      sections[cmd.section!].push(cmd);
    });
    return sections;
  }, [results]);

  return (
    <>
      {open && <div className="fixed inset-0 z-50" onClick={() => setOpen(false)} />}
      <div
        className={`fixed left-1/2 top-[15vh] z-50 w-full max-w-xl -translate-x-1/2 transform transition-all duration-200 ${
          open ? "opacity-100 scale-100" : "opacity-0 scale-95 pointer-events-none"
        }`}
      >
        <div className="bg-[var(--vbase-bg)] border border-[var(--vbase-border)] rounded-xl shadow-2xl overflow-hidden">
          <div className="flex items-center gap-3 border-b border-[var(--vbase-border)] px-4 py-3">
            <IconCommand className="h-5 w-5 text-[var(--vbase-indigo)]" />
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search commands, contacts, companies…"
              className="flex-1 h-10 bg-transparent text-sm text-[var(--vbase-slate800)] placeholder:text-[var(--vbase-slate400)] focus:outline-none"
            />
            {input && (
              <button onClick={() => setInput("")} className="text-[var(--vbase-slate400)] hover:text-[var(--vbase-slate700)]">
                <IconX className="h-4 w-4" />
              </button>
            )}
          </div>

          <div ref={listRef} className="max-h-80 overflow-y-auto p-2">
            {Object.entries(sectionHeader).map(([section, cmds]) => (
              <div key={section}>
                <div className="px-2 py-1.5 text-xs font-semibold text-[var(--vbase-slate500)]">{section}</div>
                {cmds.map((cmd) => {
                  const globalIndex = results.indexOf(cmd);
                  const isSelected = globalIndex === selectedIndex;
                  return (
                    <button
                      key={cmd.id}
                      onClick={() => {
                        if (cmd.id === "search-contacts" || cmd.id === "search-companies") {
                          const q = input.trim();
                          if (q) {
                            window.location.hash = `${cmd.href}${encodeURIComponent(q)}`;
                            setOpen(false);
                          }
                        } else {
                          window.location.hash = cmd.href;
                          setOpen(false);
                        }
                      }}
                      className={`flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-left transition-colors ${
                        isSelected
                          ? "bg-[var(--vbase-muted-bg)] text-[var(--vbase-slate900)] shadow-sm"
                          : "text-[var(--vbase-slate700)] hover:bg-[var(--vbase-bg-alt)]"
                      }`}
                      onMouseEnter={() => setSelectedIndex(globalIndex)}
                    >
                      <cmd.icon className="h-4 w-4 text-[var(--vbase-slate500)]" />
                      <span className="flex-1 text-sm">{cmd.label}</span>
                      {cmd.shortcut && (
                        <kbd className="ml-auto rounded border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--vbase-slate400)]">
                          {cmd.shortcut}
                        </kbd>
                      )}
                    </button>
                  );
                })}
              </div>
            ))}
            {results.length === 0 && (
              <div className="px-3 py-6 text-center text-sm text-[var(--vbase-slate500)]">
                No commands found
              </div>
            )}
          </div>

          <div className="border-t border-[var(--vbase-border)] px-4 py-2 text-xs text-[var(--vbase-slate400)] flex items-center gap-4">
            <span><kbd className="rounded border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-1">↑↓</kbd> navigate</span>
            <span><kbd className="rounded border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-1">↵</kbd> select</span>
            <span><kbd className="rounded border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-1">esc</kbd> close</span>
          </div>
        </div>
      </div>
    </>
  );
}
