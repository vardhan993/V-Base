export function Toast({ message, type = "info", onClose }: { message: string; type?: "success" | "error" | "info"; onClose?: () => void }) {
  return (
    <div className={`flex items-center gap-2 rounded-lg border p-3 shadow-lg ${
      type === "success" ? "border-[var(--vbase-green)]/20 bg-[var(--vbase-bg)]" : type === "error" ? "border-[var(--vbase-red)]/20 bg-[var(--vbase-bg)]" : "border-[var(--vbase-cyan)]/20 bg-[var(--vbase-bg)]"
    }`}>
      {type === "success" && <svg className="h-4 w-4 text-[var(--vbase-green)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><path d="m9 11 3 3L22 4" /></svg>}
      {type === "error" && <svg className="h-4 w-4 text-[var(--vbase-red)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><path d="m15 9-6 6M9 9l6 6" /></svg>}
      {type === "info" && <svg className="h-4 w-4 text-[var(--vbase-cyan)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" /></svg>}
      <span className="text-sm font-medium text-[var(--vbase-slate800)]">{message}</span>
      {onClose && <button onClick={onClose} className="ml-2 flex h-5 w-5 items-center justify-center rounded text-[var(--vbase-slate400)] hover:bg-[var(--vbase-border)]"><svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6 6 18M6 6l12 12" /></svg></button>}
    </div>
  );
}
