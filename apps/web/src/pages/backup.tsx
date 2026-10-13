import { useCallback, useEffect, useMemo, useState } from "react";
import {
  IconDatabase,
  IconDownload,
  IconRefreshCcw,
  IconShieldCheck,
  IconTrash2,
  IconAlertCircle,
  IconAlertTriangle,
  IconLoader2,
  IconFileSpreadsheet,
  IconServer,
  IconHistory,
  IconCopy,
  IconCheck,
  IconTerminal,
  IconLayers,
  IconHardDrive,
  IconInfo,
} from "@/lib/icons";
import { api, downloadFile, ApiError } from "@/lib/api";
import { toast, useAuthStore } from "@/lib/store";

// ---------------------------------------------------------------------------
// Contract mirrored from backend/src/nexus/api/v1/settings.py
// ---------------------------------------------------------------------------

interface Validation { valid: boolean; error?: string; tables?: number; rows?: number }
interface BackupItem {
  file: string;
  name: string;
  kind: "json" | "pg_dump";
  size_bytes: number;
  created_at: string;
  validation: Validation;
}
interface BackupList {
  backups: BackupItem[];
  count: number;
  backups_path: string;
  pg_dump_available: boolean;
}
interface AppInfo {
  app_name: string;
  tagline: string;
  version: string;
  environment: string;
  database_engine: string;
  backups_path: string;
  uploads_path: string;
  pg_dump_available: boolean;
  last_backup: { created_at?: string; kind?: string; file?: string } | null;
  database: { server_version: string | null; alembic_revision: string | null; size_bytes: number | null; host: string | null };
}
interface RestoreResult {
  status: "restored" | "manual_action_required";
  kind?: string;
  file?: string;
  restored_from?: string;
  rows_restored?: number;
  safety_snapshot?: string;
  note?: string;
  instructions?: string;
}

function fmtBytes(n: number | null | undefined) {
  if (!n) return "—";
  if (n > 1024 * 1024 * 1024) return (n / (1024 * 1024 * 1024)).toFixed(2) + " GB";
  if (n > 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + " MB";
  if (n > 1024) return Math.round(n / 1024) + " KB";
  return n + " B";
}

function fmtWhen(value: string | null | undefined) {
  if (!value) return "Never";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

// ---------------------------------------------------------------------------

export function BackupPage() {
  const { user } = useAuthStore();
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [listing, setListing] = useState<BackupList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [verifying, setVerifying] = useState<string | null>(null);
  const [confirmRestore, setConfirmRestore] = useState<BackupItem | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [restoreResult, setRestoreResult] = useState<RestoreResult | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [app, backups] = await Promise.all([
        api.get<AppInfo>("/settings/app"),
        api.get<BackupList>("/settings/backups"),
      ]);
      setInfo(app);
      setListing(backups);
    } catch (e: any) {
      setError(e?.data?.detail || e?.message || "Could not load backup status");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const createBackup = async () => {
    setCreating(true);
    try {
      const res = await api.post<{ kind?: string; file?: string; size_bytes?: number }>("/settings/backup");
      toast(
        res?.kind === "pg_dump"
          ? "Physical pg_dump backup created and validated"
          : "Logical JSON snapshot created and validated",
        "success"
      );
      await load();
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Backup failed", "error");
    } finally {
      setCreating(false);
    }
  };

  const verify = async (item: BackupItem) => {
    setVerifying(item.file);
    try {
      const res = await api.post<{ validation: Validation }>("/settings/backup/verify", { backup_file: item.file });
      setListing((prev) =>
        prev
          ? {
              ...prev,
              backups: prev.backups.map((b) => (b.file === item.file ? { ...b, validation: res.validation } : b)),
            }
          : prev
      );
      toast(res.validation.valid ? `${item.name} passed validation` : `${item.name} failed validation`, res.validation.valid ? "success" : "error");
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Verification failed", "error");
    } finally {
      setVerifying(null);
    }
  };

  const restore = async (item: BackupItem) => {
    setRestoring(true);
    setRestoreResult(null);
    try {
      const res = await api.post<RestoreResult>("/settings/restore", { backup_file: item.file });
      setRestoreResult(res);
      if (res.status === "restored") {
        toast(`Restored ${res.rows_restored ?? 0} rows from ${item.name}`, "success");
      } else {
        toast("SQL dumps are restored with the command shown below", "info");
      }
      setConfirmRestore(null);
      await load();
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Restore failed", "error");
    } finally {
      setRestoring(false);
    }
  };

  const downloadExport = async () => {
    setExporting(true);
    try {
      await downloadFile("/settings/download-db", "vbase-export.json");
      toast("Portable JSON export downloaded", "success");
    } catch (e: any) {
      toast(e instanceof ApiError ? e.message : "Export failed", "error");
    } finally {
      setExporting(false);
    }
  };

  const latest = listing?.backups?.[0];
  const host = info?.database?.host ?? "your-postgres-host";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Backup &amp; Restore</h1>
          <p className="mt-0.5 text-sm text-[var(--vbase-slate500)]">
            PostgreSQL snapshots, physical dumps, verification and recovery procedures.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={downloadExport} disabled={exporting} className="vbase-btn-secondary flex items-center gap-1.5">
            {exporting ? <IconLoader2 className="h-4 w-4 animate-spin" /> : <IconDownload className="h-4 w-4" />}
            <span>Download export</span>
          </button>
          <button onClick={createBackup} disabled={creating} className="vbase-btn-primary flex items-center gap-1.5">
            {creating ? <IconLoader2 className="h-4 w-4 animate-spin" /> : <IconDatabase className="h-4 w-4" />}
            <span>Backup now</span>
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col items-center gap-2 py-20 text-sm text-[var(--vbase-slate500)]">
          <IconLoader2 className="h-6 w-6 animate-spin text-[var(--vbase-indigo)]" />
          Reading PostgreSQL status…
        </div>
      ) : error ? (
        <div className="flex flex-col items-center gap-3 py-20 text-sm text-[var(--vbase-red)]">
          <IconAlertCircle className="h-6 w-6" />
          {error}
          <button onClick={load} className="vbase-btn-secondary">
            Retry
          </button>
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Fact label="Backups stored" value={String(listing?.count ?? 0)} />
            <Fact label="Latest backup" value={fmtWhen(latest?.created_at)} hint={latest?.name} />
            <Fact label="Database size" value={fmtBytes(info?.database?.size_bytes)} />
            <Fact
              label="pg_dump"
              value={info?.pg_dump_available ? "Available" : "Not installed"}
              hint={info?.pg_dump_available ? "Physical dumps enabled" : "Logical JSON snapshots"}
              tone={info?.pg_dump_available ? "green" : "amber"}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="vbase-card p-5 lg:col-span-2">
              <h2 className="mb-3 flex items-center gap-2 font-semibold text-[var(--vbase-slate800)]">
                <IconServer className="h-4 w-4" />
                PostgreSQL target
              </h2>
              <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
                <Detail label="Engine" value={info?.database_engine ?? "postgresql"} />
                <Detail label="Server version" value={info?.database?.server_version ?? "—"} />
                <Detail label="Host" value={host ?? "—"} mono />
                <Detail label="Schema revision" value={info?.database?.alembic_revision ?? "—"} mono />
                <Detail label="Backup directory" value={listing?.backups_path ?? info?.backups_path ?? "—"} mono />
                <Detail
                  label="Last scheduled backup"
                  value={info?.last_backup?.created_at ? fmtWhen(info.last_backup.created_at) : "Never"}
                />
              </div>
              <p className="mt-4 flex items-start gap-2 border-t border-[var(--vbase-border)] pt-3 text-xs text-[var(--vbase-slate500)]">
                <IconInfo className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
                On a managed free-tier host the application filesystem is ephemeral. Treat the snapshots below as a
                portable safety net and use the host's own point-in-time restore for disaster recovery — the playbook on
                the right covers both.
              </p>
            </div>

            <Playbook host={host} />
          </div>

          {restoreResult && (
            <div
              className={`vbase-card p-4 text-sm ${
                restoreResult.status === "restored" ? "border-[var(--vbase-green)]/40" : "border-[var(--vbase-amber)]/40"
              }`}
            >
              <p className="flex items-start gap-2">
                {restoreResult.status === "restored" ? (
                  <IconShieldCheck className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--vbase-green)]" />
                ) : (
                  <IconAlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--vbase-amber)]" />
                )}
                <span className="text-[var(--vbase-slate700)]">
                  {restoreResult.status === "restored" ? (
                    <>
                      Restored <strong>{restoreResult.rows_restored ?? 0}</strong> rows from{" "}
                      <code className="font-mono text-xs">{restoreResult.restored_from}</code>. A safety snapshot was
                      written to <code className="font-mono text-xs">{restoreResult.safety_snapshot}</code>{" "}
                      beforehand. {restoreResult.note}
                    </>
                  ) : (
                    restoreResult.instructions
                  )}
                </span>
              </p>
            </div>
          )}

          <div className="vbase-card overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--vbase-border)] px-4 py-3">
              <h3 className="font-semibold text-[var(--vbase-slate800)]">
                Available backups ({listing?.count ?? 0})
              </h3>
              <button onClick={load} className="vbase-btn-ghost flex items-center gap-1.5">
                <IconRefreshCcw className="h-4 w-4" />
                <span>Refresh</span>
              </button>
            </div>

            <div className="divide-y divide-[var(--vbase-border)]">
              {(listing?.backups ?? []).map((b) => (
                <div key={b.file} className="flex flex-wrap items-center gap-3 px-4 py-3">
                  <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md bg-[var(--vbase-bg-alt)]">
                    {b.kind === "pg_dump" ? (
                      <IconTerminal className="h-4 w-4 text-[var(--vbase-slate500)]" />
                    ) : (
                      <IconFileSpreadsheet className="h-4 w-4 text-[var(--vbase-slate500)]" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-[var(--vbase-slate800)]">{b.name}</p>
                    <p className="text-xs text-[var(--vbase-slate500)]">
                      {fmtBytes(b.size_bytes)} · {fmtWhen(b.created_at)} ·{" "}
                      {b.kind === "pg_dump" ? "physical SQL dump" : "logical JSON snapshot"}
                    </p>
                  </div>

                  {b.validation?.valid ? (
                    <span className="flex items-center gap-1 rounded-full bg-[var(--vbase-green)]/10 px-2 py-0.5 text-xs font-medium text-[var(--vbase-green)]">
                      <IconCheck className="h-3 w-3" />
                      Valid
                      {b.validation.rows ? ` · ${b.validation.rows} rows` : ""}
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 rounded-full bg-[var(--vbase-red)]/10 px-2 py-0.5 text-xs font-medium text-[var(--vbase-red)]">
                      <IconAlertCircle className="h-3 w-3" />
                      {b.validation?.error ? "Invalid" : "Unverified"}
                    </span>
                  )}

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => verify(b)}
                      disabled={verifying === b.file}
                      className="vbase-btn-ghost flex items-center gap-1.5 text-xs"
                    >
                      {verifying === b.file ? (
                        <IconLoader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <IconShieldCheck className="h-3.5 w-3.5" />
                      )}
                      <span>Verify</span>
                    </button>
                    <button
                      onClick={() => setConfirmRestore(b)}
                      disabled={!b.validation?.valid}
                      className="vbase-btn-secondary flex items-center gap-1.5 text-xs"
                    >
                      <IconRefreshCcw className="h-3.5 w-3.5" />
                      <span>Restore</span>
                    </button>
                  </div>
                </div>
              ))}

              {!listing?.backups?.length && (
                <div className="flex flex-col items-center gap-2 px-4 py-14 text-center text-sm text-[var(--vbase-slate500)]">
                  <IconDatabase className="h-8 w-8 text-[var(--vbase-slate300)]" />
                  No backups yet — create one with “Backup now”.
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {confirmRestore && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-lg rounded-xl border border-[var(--vbase-border)] bg-[var(--vbase-bg)] p-6 shadow-xl">
            <h3 className="flex items-center gap-2 text-lg font-semibold text-[var(--vbase-slate900)]">
              <IconAlertTriangle className="h-5 w-5 text-[var(--vbase-amber)]" />
              Restore {confirmRestore.name}?
            </h3>
            <div className="mt-3 space-y-2 text-sm text-[var(--vbase-slate600)]">
              <p>
                Every row in <strong>{confirmRestore.name}</strong> is re-inserted and sequence counters are reset inside
                a single transaction. A safety snapshot of the current database is always written first.
              </p>
              {confirmRestore.kind === "pg_dump" ? (
                <p className="rounded-md border border-[var(--vbase-amber)]/30 bg-[var(--vbase-amber)]/5 px-3 py-2 text-xs">
                  This is a physical SQL dump. V-Base will not execute it in-process — it returns the exact
                  <code className="mx-1 font-mono">pg_restore</code> / <code className="mx-1 font-mono">psql</code>{" "}
                  command for you to run deliberately.
                </p>
              ) : (
                <p className="rounded-md border border-[var(--vbase-red)]/25 bg-[var(--vbase-red)]/5 px-3 py-2 text-xs text-[var(--vbase-red)]">
                  Records created after this snapshot will not exist afterwards. Only your account's sessions are
                  preserved.
                </p>
              )}
              {!user?.is_superuser && (
                <p className="rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-3 py-2 text-xs">
                  Restore requires an administrator account. You are signed in as a member, so the API will refuse this
                  request.
                </p>
              )}
            </div>
            <div className="mt-5 flex items-center justify-end gap-2">
              <button onClick={() => setConfirmRestore(null)} className="vbase-btn-ghost">
                Cancel
              </button>
              <button
                onClick={() => restore(confirmRestore)}
                disabled={restoring || !user?.is_superuser}
                className="vbase-btn-danger flex items-center gap-1.5"
              >
                {restoring ? <IconLoader2 className="h-4 w-4 animate-spin" /> : <IconTrash2 className="h-4 w-4" />}
                <span>Restore from this backup</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------

function Fact({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "green" | "amber";
}) {
  return (
    <div className="vbase-card px-4 py-3">
      <p className="text-xs uppercase tracking-wider text-[var(--vbase-slate500)]">{label}</p>
      <p
        className={`mt-1 truncate text-lg font-semibold ${
          tone === "green"
            ? "text-[var(--vbase-green)]"
            : tone === "amber"
            ? "text-[var(--vbase-amber)]"
            : "text-[var(--vbase-slate900)]"
        }`}
      >
        {value}
      </p>
      {hint && <p className="mt-0.5 truncate font-mono text-[10px] text-[var(--vbase-slate400)]">{hint}</p>}
    </div>
  );
}

function Detail({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="border-b border-[var(--vbase-border)] py-2 last:border-0">
      <p className="text-xs uppercase tracking-wider text-[var(--vbase-slate500)]">{label}</p>
      <p className={`mt-0.5 truncate text-sm text-[var(--vbase-slate700)] ${mono ? "font-mono text-[11px]" : ""}`}>
        {value}
      </p>
    </div>
  );
}

/**
 * Recovery playbook. Commands are derived from the live configuration so the
 * document the operator copies is the one that matches this deployment.
 */
function Playbook({ host }: { host: string }) {
  const steps = useMemo(
    () => [
      {
        icon: <IconLayers className="h-4 w-4" />,
        title: "1 · Snapshot before you change anything",
        body: "Settings → Backup → “Backup now”, or from a shell:",
        command: "python -m nexus.commands.backup",
      },
      {
        icon: <IconTerminal className="h-4 w-4" />,
        title: "2 · Physical dump (needs pg_dump on the host)",
        body: "Produces the artifact pg_restore consumes. Never commit the dump — it contains business data.",
        command: `pg_dump --no-owner --no-privileges -Fc -h ${host} -d vbase -f vbase.dump`,
      },
      {
        icon: <IconDatabase className="h-4 w-4" />,
        title: "3 · Restore a physical dump",
        body: "Drop and recreate into a clean database, then re-run migrations to confirm the schema revision.",
        command: `pg_restore --clean --if-exists --no-owner -h ${host} -d vbase vbase.dump`,
      },
      {
        icon: <IconHistory className="h-4 w-4" />,
        title: "4 · Re-apply schema migrations",
        body: "Migrations are the only supported way to change the schema; they are idempotent to the current head.",
        command: "alembic -c backend/alembic.ini upgrade head",
      },
      {
        icon: <IconShieldCheck className="h-4 w-4" />,
        title: "5 · Verify the restore",
        body: "The readiness probe confirms PostgreSQL answers and that a schema revision is present.",
        command: "curl -s http://127.0.0.1:8000/health/ready",
      },
      {
        icon: <IconServer className="h-4 w-4" />,
        title: "6 · Managed-host recovery (Neon / Render)",
        body: "Neon Free keeps a short point-in-time window and instant branches; use the console to restore or fork rather than replaying a dump. On Render, redeploy the API and re-run migrations — the database itself lives on the external Postgres provider.",
        command: null,
      },
    ],
    [host]
  );

  return (
    <div className="vbase-card p-5">
      <h2 className="mb-3 flex items-center gap-2 font-semibold text-[var(--vbase-slate800)]">
        <IconHardDrive className="h-4 w-4" />
        Recovery playbook
      </h2>
      <ol className="space-y-4">
        {steps.map((s) => (
          <li key={s.title}>
            <p className="flex items-center gap-2 text-sm font-medium text-[var(--vbase-slate800)]">
              <span className="text-[var(--vbase-indigo)]">{s.icon}</span>
              {s.title}
            </p>
            <p className="mt-1 text-xs leading-relaxed text-[var(--vbase-slate500)]">{s.body}</p>
            {s.command && <CommandLine command={s.command} />}
          </li>
        ))}
      </ol>
      <p className="mt-4 border-t border-[var(--vbase-border)] pt-3 text-xs text-[var(--vbase-slate500)]">
        Full details, including provider-specific steps, live in{" "}
        <code className="font-mono">docs/BACKUP.md</code>.
      </p>
    </div>
  );
}

function CommandLine({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      toast("Clipboard unavailable in this browser", "error");
    }
  };
  return (
    <div className="mt-1.5 flex items-start gap-2 rounded-md bg-[var(--vbase-slate900)] px-2.5 py-2">
      <code className="min-w-0 flex-1 break-all font-mono text-[11px] leading-relaxed text-[var(--vbase-slate100)]">
        {command}
      </code>
      <button
        onClick={copy}
        aria-label="Copy command"
        className="flex-shrink-0 rounded p-1 text-[var(--vbase-slate400)] transition-colors hover:bg-white/10 hover:text-white"
      >
        {copied ? <IconCheck className="h-3.5 w-3.5" /> : <IconCopy className="h-3.5 w-3.5" />}
      </button>
    </div>
  );
}
