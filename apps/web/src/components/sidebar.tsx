import React from "react";
import { Link, useLocation } from "react-router-dom";
import { useSidebarStore, useAuthStore } from "@/lib/store";
import {
  IconLayoutDashboard,
  IconBuilding2,
  IconUsers,
  IconTable2,
  IconHash,
  IconSearch,
  IconFileSpreadsheet,
  IconAlertTriangle,
  IconSparkles,
  IconActivity,
  IconSettings,
  IconStar,
  IconSparkle,
  IconTag,
  IconDatabase,
  IconBracesIcon,
  IconColumns3,
  IconListChecks,
  IconSidebarCollapse,
  IconSidebarExpand,
  IconMailPlus,
} from "@/lib/icons";

/** One entry per route; grouped so 20 links stay scannable. */
const GROUPS: { label: string; items: { to: string; label: string; icon: any; exact?: boolean }[] }[] = [
  {
    label: "Overview",
    items: [
      { to: "/dashboard", label: "Dashboard", icon: IconLayoutDashboard, exact: true },
      { to: "/pipeline", label: "Pipeline", icon: IconColumns3 },
      { to: "/tasks", label: "Follow-ups", icon: IconListChecks },
      { to: "/leads", label: "Leads", icon: IconSparkle },
    ],
  },
  {
    label: "Records",
    items: [
      { to: "/companies", label: "Companies", icon: IconBuilding2 },
      { to: "/contacts", label: "Contacts", icon: IconUsers },
      { to: "/all-records", label: "All Records", icon: IconTable2 },
      { to: "/lists", label: "Lists", icon: IconHash },
      { to: "/tags", label: "Tags", icon: IconTag },
      { to: "/custom-fields", label: "Custom Fields", icon: IconBracesIcon },
    ],
  },
  {
    label: "Workspace",
    items: [
      { to: "/import", label: "Import Center", icon: IconFileSpreadsheet },
      { to: "/duplicates", label: "Duplicates", icon: IconAlertTriangle },
      { to: "/data-quality", label: "Data Quality", icon: IconSparkles },
      { to: "/saved-searches", label: "Saved Searches", icon: IconSearch },
      { to: "/saved-views", label: "Saved Views", icon: IconStar },
    ],
  },
  {
    label: "Outreach",
    items: [
      { to: "/sequences", label: "Sequences", icon: IconMailPlus },
      { to: "/analytics", label: "Analytics", icon: IconActivity },
      { to: "/activity", label: "Activity", icon: IconActivity },
      { to: "/backup", label: "Backup & Restore", icon: IconDatabase },
      { to: "/billing", label: "Plan & Billing", icon: IconStar, exact: false },
      { to: "/settings", label: "Settings", icon: IconSettings },
    ],
  },
  {
    label: "Campaigns",
    items: [
      { to: "/campaigns", label: "Campaigns", icon: IconMailPlus },
    ],
  },
];

export function Sidebar() {
  const { collapsed, toggle, mobileOpen, setMobileOpen } = useSidebarStore();
  const location = useLocation();

  // Any navigation closes the phone drawer.
  React.useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname, setMobileOpen]);

  return (
    <>
    {/* Phone drawer backdrop */}
    {mobileOpen && (
      <div
        className="fixed inset-0 z-40 bg-black/40 md:hidden"
        onClick={() => setMobileOpen(false)}
        aria-hidden="true"
      />
    )}
    {/* One aside, two behaviours: off-canvas drawer on phones, rail on desktop. */}
    <aside
      className={`fixed left-0 top-0 h-screen flex-col bg-[var(--vbase-sidebar-bg)] border-r border-[var(--vbase-border-dark)] transition-transform duration-200 md:flex md:translate-x-0 md:z-30 ${
        mobileOpen ? "z-50 flex translate-x-0" : "-translate-x-full hidden md:block"
      }`}
      style={{ width: collapsed ? 68 : 224 }}
    >
      {/* Brand tile: gradient plate with the data-cells mark. */}
      <div className="flex h-14 flex-shrink-0 items-center gap-3 border-b border-[var(--vbase-border-dark)] px-3">
        <div
          className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-white shadow-[0_0_12px_-2px_rgba(99,102,241,0.8)]"
          style={{ backgroundImage: "linear-gradient(135deg, var(--vbase-brand-a), var(--vbase-brand-b))" }}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 4h3v7H4z" />
            <path d="M9 4h3v4H9z" />
            <path d="M9 10h3v2h-3z" />
          </svg>
        </div>
        {!collapsed && (
          <div className="min-w-0 leading-tight">
            <span className="block truncate text-[15px] font-semibold tracking-tight text-white">V-Base</span>
            <span className="block truncate text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--vbase-slate500)]">
              Business intelligence
            </span>
          </div>
        )}
        <button
          onClick={toggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="ml-auto flex h-6 w-6 flex-shrink-0 items-center justify-center rounded text-[var(--vbase-slate500)] hover:text-white hover:bg-white/5 transition-colors"
        >
          {collapsed ? <IconSidebarExpand className="h-4 w-4" /> : <IconSidebarCollapse className="h-4 w-4" />}
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto pb-3 pt-1 px-2">
        {GROUPS.map((group) => (
          <div key={group.label}>
            {!collapsed && <div className="vbase-sidebar-group">{group.label}</div>}
            {collapsed && <div className="mx-auto my-3 h-px w-8 bg-white/10" />}
            {group.items.map((item) => {
              const isActive = item.exact
                ? location.pathname === item.to
                : location.pathname.startsWith(item.to);
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`relative flex items-center gap-3 rounded-lg px-2.5 py-[7px] text-sm font-medium transition-colors ${
                    isActive ? "text-white" : "text-[var(--vbase-slate400)] hover:bg-white/5 hover:text-white"
                  }`}
                  title={collapsed ? item.label : undefined}
                >
                  {isActive && (
                    <>
                      <span className="absolute inset-0 rounded-lg bg-[var(--vbase-sidebar-active)]" />
                      <span
                        className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full"
                        style={{ backgroundImage: "linear-gradient(180deg, var(--vbase-brand-a), var(--vbase-brand-b))" }}
                      />
                    </>
                  )}
                  <item.icon
                    className={`relative h-[18px] w-[18px] flex-shrink-0 ${isActive ? "text-[var(--vbase-indigo)]" : ""}`}
                  />
                  {!collapsed && <span className="relative">{item.label}</span>}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="flex-shrink-0 border-t border-[var(--vbase-border-dark)] p-3">
        <div
          className={`flex items-center gap-2 rounded-lg bg-white/[0.04] px-2.5 py-2 text-[11px] ${
            collapsed ? "justify-center" : ""
          }`}
        >
          <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-[var(--vbase-green)]" />
          {!collapsed && <PlanBadge />}
        </div>
      </div>
    </aside>
    </>
  );
}

/** Plan chip: the owner's admin email is free forever; others show INR price. */
function PlanBadge() {
  const user = useAuthStore((s) => s.user);
  const plan = user?.plan || "starter";
  const meta: Record<string, string> = {
    admin: "Admin · unlimited & free",
    starter: "Starter · ₹499/mo",
    growth: "Growth · ₹1,499/mo",
    scale: "Scale · ₹3,999/mo",
  };
  return (
    <span className="truncate text-[var(--vbase-slate500)]">{meta[plan] || plan}</span>
  );
}
