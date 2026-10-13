import { useToastStore } from "@/lib/store";
import { IconCheckCircle2, IconAlertCircle, IconInfo } from "@/lib/icons";

export function ToastStack() {
  const { toasts, remove } = useToastStore();

  return (
    <div className="fixed right-4 top-4 z-[60] flex flex-col gap-2 w-84">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex items-start gap-3 rounded-lg border bg-[var(--vbase-bg)] p-3 shadow-lg backdrop-blur-sm ${
            t.type === "success"
              ? "border-[var(--vbase-green)]/20"
              : t.type === "error"
              ? "border-[var(--vbase-red)]/20"
              : "border-[var(--vbase-cyan)]/20"
          }`}
        >
          <div className={`mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full ${
            t.type === "success"
              ? "bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]"
              : t.type === "error"
              ? "bg-[var(--vbase-red)]/10 text-[var(--vbase-red)]"
              : "bg-[var(--vbase-cyan)]/10 text-[var(--vbase-cyan)]"
          }`}>
            {t.type === "success" && <IconCheckCircle2 className="h-4 w-4" />}
            {t.type === "error" && <IconAlertCircle className="h-4 w-4" />}
            {t.type === "info" && <IconInfo className="h-4 w-4" />}
          </div>
          <div className="flex min-w-0 flex-1 flex-col">
            <p className="text-sm font-medium text-[var(--vbase-slate800)]">{t.message}</p>
          </div>
          <button onClick={() => remove(t.id)} className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full text-[var(--vbase-slate400)] hover:bg-[var(--vbase-border)] hover:text-[var(--vbase-slate600)]">
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6 6 18M6 6l12 12" /></svg>
          </button>
        </div>
      ))}
    </div>
  );
}
