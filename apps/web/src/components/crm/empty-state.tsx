import { IconPlus, IconSearch, IconCheck } from "@/lib/icons";

export interface EmptyStateProps {
  icon: "company" | "contact" | "task";
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function EmptyState({ icon, title, description, actionLabel, onAction }: EmptyStateProps) {
  const glyph =
    icon === "company" ? (
      <IconPlus className="h-5 w-5 text-[var(--vbase-slate400)]" />
    ) : icon === "task" ? (
      <IconCheck className="h-5 w-5 text-[var(--vbase-slate400)]" />
    ) : (
      <IconSearch className="h-5 w-5 text-[var(--vbase-slate400)]" />
    );

  return (
    <div className="flex flex-col items-center gap-3 py-16 text-center text-sm text-[var(--vbase-slate500)]">
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--vbase-bg-alt)]">
        {glyph}
      </div>
      <p className="font-medium text-[var(--vbase-slate700)]">{title}</p>
      {description && <p>{description}</p>}
      {actionLabel && onAction && (
        <button onClick={onAction} className="mt-1 flex items-center gap-1.5 rounded-md bg-[var(--vbase-indigo)] px-3 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-[var(--vbase-indigo-hover)]">
          <IconPlus className="h-4 w-4" />
          {actionLabel}
        </button>
      )}
    </div>
  );
}
