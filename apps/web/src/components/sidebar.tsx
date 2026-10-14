import { Link, useLocation } from "react-router-dom";
import { useSidebarStore } from "@/lib/store";
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

export function Sidebar() {
  const { collapsed, toggle } = useSidebarStore();
  const location = useLocation();

  const items = [
    { to: "/dashboard", label: "Dashboard", icon: IconLayoutDashboard, exact: true },
    { to: "/pipeline", label: "Pipeline", icon: IconColumns3 },
    { to: "/tasks", label: "Follow-ups", icon: IconListChecks },
    { to: "/leads", label: "Leads", icon: IconSparkle },
    { to: "/companies", label: "Companies", icon: IconBuilding2 },
    { to: "/contacts", label: "Contacts", icon: IconUsers },
    { to: "/all-records", label: "All Records", icon: IconTable2 },
    { to: "/lists", label: "Lists", icon: IconHash },
    { to: "/tags", label: "Tags", icon: IconTag },
    { to: "/saved-searches", label: "Saved Searches", icon: IconSearch },
    { to: "/saved-views", label: "Saved Views", icon: IconStar },
    { to: "/custom-fields", label: "Custom Fields", icon: IconBracesIcon },
    { to: "/backup", label: "Backup & Restore", icon: IconDatabase },
    { to: "/import", label: "Import Center", icon: IconFileSpreadsheet },
    { to: "/duplicates", label: "Duplicates", icon: IconAlertTriangle },
    { to: "/data-quality", label: "Data Quality", icon: IconSparkles },
    { to: "/analytics", label: "Analytics", icon: IconActivity },
    { to: "/sequences", label: "Sequences", icon: IconMailPlus },
    { to: "/activity", label: "Activity", icon: IconActivity },
    { to: "/settings", label: "Settings", icon: IconSettings },
  ];

  return (
    <aside className="fixed left-0 top-0 z-30 flex h-screen w-[220px] flex-col bg-[var(--vbase-sidebar-bg)] border-r border-[var(--vbase-border-dark)] transition-all duration-200" style={{ width: collapsed ? 68 : 220 }}>
      <div className="flex h-14 items-center gap-3 border-b border-[var(--vbase-border-dark)] px-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-[var(--vbase-indigo)] text-white shadow-sm">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 4h3v7H4z" />
            <path d="M9 4h3v4H9z" />
            <path d="M9 10h3v2h-3z" />
          </svg>
        </div>
        {!collapsed && (
          <span className="text-sm font-semibold tracking-tight text-white">V-Base</span>
        )}
        <button onClick={toggle} className="ml-auto flex h-6 w-6 items-center justify-center rounded text-[var(--vbase-slate400)] hover:text-white hover:bg-white/5 transition-colors">
          {collapsed ? <IconSidebarExpand className="h-4 w-4" /> : <IconSidebarCollapse className="h-4 w-4" />}
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto py-3 px-2">
        {items.map((item) => {
          const isActive = item.exact ? location.pathname === item.to : location.pathname.startsWith(item.to);
          return (
            <Link
              key={item.to}
              to={item.to}
              className={`flex items-center gap-3 rounded-md px-2 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-[var(--vbase-sidebar-active)] text-white"
                  : "text-[var(--vbase-slate400)] hover:bg-white/5 hover:text-white"
              }`}
              title={collapsed ? item.label : undefined}
            >
              <item.icon className={`h-5 w-5 flex-shrink-0 ${isActive ? "text-[var(--vbase-indigo)]" : ""}`} />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-[var(--vbase-border-dark)] p-3">
        {!collapsed && (
          <div className="text-xs text-[var(--vbase-slate500)]">
            Free & local-first
          </div>
        )}
      </div>
    </aside>
  );
}
