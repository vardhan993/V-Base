import { useState, useRef, useEffect } from "react";
import { IconMoreHorizontal, IconArchive, IconRefreshCcw, IconTrash2, IconPencil, IconExternalLink } from "@/lib/icons";

export interface EntityActionsProps {
  /** Record kind, used for the delete confirmation text. */
  entityType?: string;
  /** Record id, unused by the menu itself but required by callers for context. */
  id?: number;
  /** Display name shown in the delete confirmation. */
  name?: string;
  archived: boolean;
  onArchive: () => void;
  onRestore: () => void;
  onDelete: () => void;
  /** Open the record's full editor. Omit to hide the item. */
  onEdit?: () => void;
  /** Open the record's detail view. Omit to hide the item. */
  onOpen?: () => void;
}

export function EntityActions({
  entityType,
  name,
  archived,
  onArchive,
  onRestore,
  onDelete,
  onEdit,
  onOpen,
}: EntityActionsProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const confirmDelete = () => {
    const what = name ? `${entityType || "record"} “${name}”` : `this ${entityType || "record"}`;
    if (window.confirm(`Delete ${what}? This cannot be undone.`)) {
      setOpen(false);
      onDelete();
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="vbase-btn vbase-btn-icon vbase-btn-ghost"
        title="Record actions"
        aria-label="Record actions"
        aria-expanded={open}
      >
        <IconMoreHorizontal className="h-4 w-4" />
      </button>

      {open && (
        <div
          className="absolute right-0 top-9 z-50 min-w-[196px] rounded-lg border border-[var(--vbase-border)] bg-[var(--vbase-bg)] py-1.5 shadow-[0_10px_30px_-8px_rgba(0,0,0,0.18)] animate-in fast"
          role="menu"
        >
          {onOpen && (
            <div className="py-1">
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  onOpen();
                }}
                className="flex w-full items-center gap-2.5 rounded-md px-3 py-1.5 text-sm font-medium text-[var(--vbase-slate700)] transition-colors hover:bg-[var(--vbase-muted-bg)]"
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-current/20 bg-current/10">
                  <IconExternalLink className="h-3.5 w-3.5" />
                </span>
                <span className="flex flex-col flex-1 gap-0.5">
                  <span className="font-medium">Open record</span>
                  <span className="text-xs opacity-70">View the full record and history</span>
                </span>
              </button>
            </div>
          )}
          {onEdit && (
            <div className="py-1">
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  onEdit();
                }}
                className="flex w-full items-center gap-2.5 rounded-md px-3 py-1.5 text-sm font-medium text-[var(--vbase-indigo)] transition-colors hover:bg-[var(--vbase-muted-bg)]"
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-current/20 bg-current/10">
                  <IconPencil className="h-3.5 w-3.5" />
                </span>
                <span className="flex flex-col flex-1 gap-0.5">
                  <span className="font-medium">Edit record</span>
                  <span className="text-xs opacity-70">Change any field on this record</span>
                </span>
              </button>
            </div>
          )}
          <div className="py-1">
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                archived ? onRestore() : onArchive();
              }}
              className={`flex w-full items-center gap-2.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors hover:bg-[var(--vbase-muted-bg)] ${
                archived
                  ? "text-[var(--vbase-green)]"
                  : "text-[var(--vbase-amber)]"
              }`}
            >
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-current/20 bg-current/10">
                {archived ? <IconRefreshCcw className="h-3.5 w-3.5" /> : <IconArchive className="h-3.5 w-3.5" />}
              </span>
              <span className="flex flex-col flex-1 gap-0.5">
                <span className="font-medium">{archived ? "Restore record" : "Archive record"}</span>
                <span className="text-xs opacity-70">{archived ? "Unarchive and make it visible again" : "Hide this record without deleting it"}</span>
              </span>
            </button>
          </div>
          <div className="my-1 border-t border-[var(--vbase-border)]" />
          <button
            type="button"
            onClick={confirmDelete}
            className="flex w-full items-center gap-2.5 rounded-md px-3 py-1.5 text-sm font-medium text-[var(--vbase-red)] transition-colors hover:bg-[var(--vbase-red)]/5"
          >
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-current/20 bg-current/10">
              <IconTrash2 className="h-3.5 w-3.5" />
            </span>
            <span className="flex flex-col flex-1 gap-0.5">
              <span className="font-medium">Delete record</span>
              <span className="text-xs opacity-70">Remove it permanently. This cannot be undone.</span>
            </span>
          </button>
        </div>
      )}
    </div>
  );
}
