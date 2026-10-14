import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  IconDatabase,
  IconShield,
  IconSettings,
  IconServer,
  IconKeyRound,
  IconMonitorSmartphone,
  IconUsers,
  IconRefreshCcw,
  IconCheck,
  IconX,
  IconLoader2,
  IconAlertCircle,
  IconInfo,
  IconHardDrive,
  IconUserPlus,
  IconArrowRight,
  IconSend,
  IconMail,
} from "@/lib/icons";
import { api } from "@/lib/api";
import { useAuthStore, useThemeStore, toast } from "@/lib/store";
import type { ThemeMode } from "@/lib/store";
import { PROVIDER_LABELS } from "@/components/crm";
import type { EmailStatus } from "@/components/crm";

// ---------------------------------------------------------------------------
// Types mirror the FastAPI response models exactly.
// ---------------------------------------------------------------------------

interface AppInfo {
  app_name: string;
  tagline: string;
  version: string;
  environment: string;
  database_engine: string;
  uploads_path: string;
  backups_path: string;
  pg_dump_available: boolean;
  pg_dump_binary: string | null;
  last_backup: { created_at?: string; kind?: string; file?: string } | null;
  database: {
    server_version: string | null;
    alembic_revision: string | null;
    size_bytes: number | null;
    host: string | null;
  };
}

interface SessionInfo {
  id: number;
  created_at: string;
  expires_at: string;
  last_seen_at: string | null;
  ip_address: string | null;
  user_agent: string | null;
  current?: boolean;
}

interface UserRow {
  id: number;
  email: string;
  username: string;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
  last_login_at: string | null;
}

const TABS = [
  { id: "general", label: "General", icon: IconSettings },
  { id: "database", label: "PostgreSQL", icon: IconDatabase },
  { id: "security", label: "Security", icon: IconShield },
  { id: "sessions", label: "Sessions", icon: IconMonitorSmartphone },
  { id: "preferences", label: "Preferences", icon: IconKeyRound },
  { id: "users", label: "Users", icon: IconUsers },
] as const;

type TabId = (typeof TABS)[number]["id"];

function fmtBytes(n: number | null | undefined) {
  if (!n) return "—";
  if (n > 1024 * 1024 * 1024) return (n / (1024 * 1024 * 1024)).toFixed(2) + " GB";
  if (n > 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + " MB";
  if (n > 1024) return Math.round(n / 1024) + " KB";
  return n + " B";
}

function fmtWhen(value: string | null | undefined) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}

function deviceLabel(ua: string | null) {
  if (!ua) return "Unknown device";
  if (/edg/i.test(ua)) return "Microsoft Edge";
  if (/chrome/i.test(ua) && !/chromium/i.test(ua)) return "Chrome";
  if (/firefox/i.test(ua)) return "Firefox";
  if (/safari/i.test(ua)) return "Safari";
  if (/curl|httpx|python|node/i.test(ua)) return "API client";
  return ua.slice(0, 48);
}

export function SettingsPage() {
  const [tab, setTab] = useState<TabId>("general");
  const { user, setUser } = useAuthStore();
  const location = useLocation();
  const navigate = useNavigate();

  // The Gmail connect flow ends with a redirect back here. Report the outcome
  // once, then strip the query so a refresh does not replay the toast.
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const outcome = params.get("email");
    if (!outcome) return;
    if (outcome === "connected") {
      toast("Gmail connected — sending is ready", "success");
    } else {
      toast(params.get("reason") || "Could not connect the mailbox", "error");
    }
    navigate({ pathname: location.pathname }, { replace: true });
  }, [location.pathname, location.search, navigate]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Settings</h1>
        <p className="mt-0.5 text-sm text-[var(--vbase-slate500)]">
          Application, PostgreSQL, security, sessions, preferences and users.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b border-[var(--vbase-border)] pb-2">
        {TABS.filter((t) => t.id !== "users" || user?.is_superuser).map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
              tab === t.id
                ? "bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]"
                : "text-[var(--vbase-slate600)] hover:bg-[var(--vbase-bg-alt)]"
            }`}
          >
            <t.icon className="h-4 w-4" />
            <span>{t.label}</span>
          </button>
        ))}
      </div>

      {tab === "general" && <GeneralTab />}
      {tab === "database" && <DatabaseTab />}
      {tab === "security" && <SecurityTab />}
      {tab === "sessions" && <SessionsTab />}
      {tab === "preferences" && <PreferencesTab onSaved={(prefs) => setUser({ ...user, preferences: prefs })} />}
      {tab === "users" && user?.is_superuser && <UsersTab currentUserId={user?.id} />}
    </div>
  );
}

// ---------------------------------------------------------------------------

function useAppInfo() {
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setInfo(await api.get<AppInfo>("/settings/app"));
    } catch (e: any) {
      setError(e?.data?.detail || e?.message || "Could not load application info");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { info, loading, error, reload: load };
}

function GeneralTab() {
  const { info, loading, error } = useAppInfo();

  if (loading) return <TabLoading label="Loading application info…" />;
  if (error) return <TabError message={error} />;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Application" icon={<IconSettings className="h-4 w-4" />}>
        <Field label="App name" value={info?.app_name ?? "V-Base"} />
        <Field label="Tagline" value={info?.tagline ?? "Your Business Data. One Powerful Base."} />
        <Field label="Version" value={info?.version ?? "—"} />
        <Field label="Environment" value={info?.environment ?? "—"} />
        <Field label="Database engine" value={info?.database_engine ?? "postgresql"} />
      </Card>

      <Card title="Files & maintenance" icon={<IconHardDrive className="h-4 w-4" />}>
        <Field label="Uploads directory" value={info?.uploads_path ?? "—"} mono />
        <Field label="Backups directory" value={info?.backups_path ?? "—"} mono />
        <Field
          label="pg_dump available"
          value={
            info?.pg_dump_available
              ? "Yes — physical dumps enabled"
              : "No — falling back to validated JSON snapshots"
          }
        />
        {info?.pg_dump_binary && <Field label="pg_dump binary" value={info.pg_dump_binary} mono />}
        <Field label="Last backup" value={info?.last_backup?.created_at ? fmtWhen(info.last_backup.created_at) : "Never"} />
        <div className="pt-2">
          <Link to="/backup" className="vbase-btn-secondary inline-flex items-center gap-1.5">
            <IconDatabase className="h-4 w-4" />
            <span>Open Backup &amp; Restore</span>
            <IconArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </Card>

      <EmailCard />
    </div>
  );
}

/** Live status of outbound email, with the exact next step when unconfigured. */
function EmailCard() {
  const { user } = useAuthStore();
  const [status, setStatus] = useState<EmailStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setStatus(await api.get<EmailStatus>("/email/status"));
    } catch (e: any) {
      setError(e?.data?.detail || e?.message || "Could not read email status");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const chooseProvider = async (provider: string) => {
    setBusy(true);
    try {
      await api.post("/settings/keys", { key: "email_provider", value: provider });
      toast(`Email provider set to ${provider}`, "success");
      await load();
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Could not change the provider", "error");
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!window.confirm("Disconnect the mailbox? Google's permission is not revoked, but V-Base forgets the token.")) {
      return;
    }
    setBusy(true);
    try {
      await api.post("/email/gmail/disconnect");
      toast("Mailbox disconnected", "success");
      await load();
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Could not disconnect", "error");
    } finally {
      setBusy(false);
    }
  };

  const credentialSource =
    status?.credential_source === "environment"
      ? "From the API environment"
      : status?.credential_source === "settings"
      ? "Stored in settings"
      : "Not set";

  const isGmail = status?.provider === "gmail";

  return (
    <Card title="Email sending" icon={<IconSend className="h-4 w-4" />}>
      {loading ? (
        <p className="flex items-center gap-2 text-sm text-[var(--vbase-slate500)]">
          <IconLoader2 className="h-4 w-4 animate-spin" />
          Checking the provider…
        </p>
      ) : (
        <>
          <div className="flex items-start justify-between gap-4 border-b border-[var(--vbase-border)] py-2.5">
            <span className="text-xs uppercase tracking-wider text-[var(--vbase-slate500)]">Provider</span>
            <select
              value={status?.provider ?? status?.default_provider ?? "resend"}
              onChange={(e) => chooseProvider(e.target.value)}
              disabled={busy}
              aria-label="Email provider"
              className="vbase-select w-56"
            >
              {(status?.supported_providers ?? ["resend"]).map((p) => (
                <option key={p} value={p}>
                  {PROVIDER_LABELS[p] ?? p}
                </option>
              ))}
            </select>
          </div>
          <Field
            label="Status"
            value={status?.configured ? "Ready — sending enabled" : "Not configured"}
          />
          <Field label="From address" value={status?.from_email ?? "—"} />
          <Field label="Credential" value={credentialSource} />
          {isGmail && <Field label="Mailbox" value={status?.gmail_connected ? "Connected" : "Not connected"} />}
          <Field
            label="Delivery tracking"
            value={
              status?.webhook_configured
                ? `Enabled · ${status?.webhook_path ?? ""}`
                : `Disabled · set EMAIL_WEBHOOK_SECRET and point the provider at ${status?.webhook_path ?? ""}`
            }
          />

          {error && <p className="pt-2 text-xs text-[var(--vbase-red)]">{error}</p>}

          {!status?.configured && !error && (
            <p className="mt-3 flex items-start gap-2 border-t border-[var(--vbase-border)] pt-3 text-xs leading-relaxed text-[var(--vbase-slate500)]">
              <IconAlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-[var(--vbase-amber)]" />
              <span>
                Still needed: <span className="font-medium">{status?.missing?.join(", ") || "credentials"}</span>. See
                the compose dialog on any contact for the exact setup steps, or set{" "}
                {(isGmail ? status?.gmail_env_vars : status?.env_vars)?.join(", ") || "EMAIL_API_KEY, EMAIL_FROM"} in
                the API environment.
              </span>
            </p>
          )}

          {isGmail && (
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-[var(--vbase-border)] pt-3">
              {status?.gmail_connected ? (
                <button
                  onClick={disconnect}
                  disabled={busy || !user?.is_superuser}
                  className="vbase-btn-secondary flex items-center gap-1.5 text-sm"
                >
                  {busy ? <IconLoader2 className="h-4 w-4 animate-spin" /> : <IconX className="h-4 w-4" />}
                  <span>Disconnect mailbox</span>
                </button>
              ) : (
                <a
                  href={status?.gmail_connect_url ?? "/api/v1/email/gmail/authorize"}
                  className={`vbase-btn-primary flex items-center gap-1.5 text-sm ${
                    user?.is_superuser ? "" : "pointer-events-none opacity-55"
                  }`}
                  aria-disabled={!user?.is_superuser}
                >
                  <IconMail className="h-4 w-4" />
                  <span>Connect Gmail</span>
                </a>
              )}
              {!user?.is_superuser && (
                <span className="text-xs text-[var(--vbase-slate500)]">
                  An administrator has to authorise the mailbox.
                </span>
              )}
            </div>
          )}
        </>
      )}
    </Card>
  );
}

function DatabaseTab() {
  const { info, loading, error, reload } = useAppInfo();

  if (loading) return <TabLoading label="Querying PostgreSQL…" />;
  if (error) return <TabError message={error} onRetry={reload} />;

  const db = info?.database;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="PostgreSQL server" icon={<IconServer className="h-4 w-4" />}>
        <Field label="Server version" value={db?.server_version ?? "—"} />
        <Field label="Host" value={db?.host ?? "—"} mono />
        <Field label="Alembic revision" value={db?.alembic_revision ?? "—"} mono />
        <Field label="Database size" value={fmtBytes(db?.size_bytes)} />
      </Card>

      <Card title="Connection safety" icon={<IconShield className="h-4 w-4" />}>
        <p className="text-sm leading-relaxed text-[var(--vbase-slate600)]">
          The browser never talks to PostgreSQL. Every query runs server-side through SQLAlchemy with bound
          parameters, and credentials live only in the API's environment variables.
        </p>
        <ul className="mt-3 space-y-2 text-sm text-[var(--vbase-slate600)]">
          <Bullet ok>PostgreSQL is enforced — SQLite and other engines are rejected at startup.</Bullet>
          <Bullet ok>Connection pooling with pre-ping and recycling for managed hosts.</Bullet>
          <Bullet ok>Prepared-statement caching disabled automatically behind PgBouncer poolers.</Bullet>
          <Bullet ok>Schema changes are applied only through Alembic migrations.</Bullet>
        </ul>
        <div className="pt-3">
          <Link to="/backup" className="vbase-btn-secondary inline-flex items-center gap-1.5">
            <IconDatabase className="h-4 w-4" />
            <span>Backup &amp; recovery</span>
          </Link>
        </div>
      </Card>
    </div>
  );
}

function SecurityTab() {
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [done, setDone] = useState(false);

  const submit = async () => {
    setPasswordError("");
    setDone(false);
    if (newPassword !== confirmPassword) {
      setPasswordError("New passwords do not match");
      return;
    }
    if (newPassword.length < 8) {
      setPasswordError("New password must be at least 8 characters");
      return;
    }
    setPasswordLoading(true);
    try {
      const res = await api.post<{ sessions_revoked: number }>("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      toast(`Password changed — ${res?.sessions_revoked ?? 0} other session(s) signed out`, "success");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setDone(true);
    } catch (e: any) {
      setPasswordError(e?.data?.detail || e?.message || "Password change failed");
    } finally {
      setPasswordLoading(false);
    }
  };

  const strength = useMemo(() => {
    let score = 0;
    if (newPassword.length >= 8) score++;
    if (newPassword.length >= 12) score++;
    if (/[A-Z]/.test(newPassword) && /[a-z]/.test(newPassword)) score++;
    if (/\d/.test(newPassword)) score++;
    if (/[^A-Za-z0-9]/.test(newPassword)) score++;
    return Math.min(score, 4);
  }, [newPassword]);

  const labels = ["Too weak", "Weak", "Fair", "Good", "Strong"];

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Change password" icon={<IconKeyRound className="h-4 w-4" />}>
        <div className="space-y-3">
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            placeholder="Current password"
            autoComplete="current-password"
            className="vbase-input"
          />
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="New password (min 8 characters)"
            autoComplete="new-password"
            className="vbase-input"
          />
          {newPassword && (
            <div className="flex items-center gap-2">
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--vbase-bg-alt)]">
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${(strength / 4) * 100}%`,
                    backgroundColor:
                      strength <= 1 ? "var(--vbase-red)" : strength === 2 ? "var(--vbase-amber, #d97706)" : "var(--vbase-green)",
                  }}
                />
              </div>
              <span className="w-16 text-xs text-[var(--vbase-slate500)]">{labels[strength]}</span>
            </div>
          )}
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Confirm new password"
            autoComplete="new-password"
            className="vbase-input"
          />
          {passwordError && (
            <p className="flex items-center gap-1.5 text-sm text-[var(--vbase-red)]">
              <IconAlertCircle className="h-4 w-4" />
              {passwordError}
            </p>
          )}
          {done && (
            <p className="flex items-center gap-1.5 text-sm text-[var(--vbase-green)]">
              <IconCheck className="h-4 w-4" />
              Password updated. Other sessions were signed out.
            </p>
          )}
          <button onClick={submit} disabled={passwordLoading} className="vbase-btn-primary flex items-center gap-1.5">
            {passwordLoading ? <IconLoader2 className="h-4 w-4 animate-spin" /> : <IconCheck className="h-4 w-4" />}
            <span>Change password</span>
          </button>
        </div>
      </Card>

      <Card title="Authentication model" icon={<IconShield className="h-4 w-4" />}>
        <ul className="space-y-2 text-sm text-[var(--vbase-slate600)]">
          <Bullet ok>Passwords hashed with a salted, slow KDF — never stored or logged in plain text.</Bullet>
          <Bullet ok>Session stored in an HttpOnly cookie, never in browser storage.</Bullet>
          <Bullet ok>CSRF double-submit token on every unsafe request.</Bullet>
          <Bullet ok>Origin allow-list rejects cross-site mutations.</Bullet>
          <Bullet ok>Per-IP sliding-window rate limiting on auth and write traffic.</Bullet>
          <Bullet ok>Trusted-host and security headers applied to every response.</Bullet>
        </ul>
      </Card>
    </div>
  );
}

function SessionsTab() {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revoking, setRevoking] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setSessions(await api.get<SessionInfo[]>("/auth/sessions"));
    } catch (e: any) {
      setError(e?.data?.detail || e?.message || "Could not load sessions");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const revokeOthers = async () => {
    setRevoking(true);
    try {
      const res = await api.delete<{ revoked: number }>("/auth/sessions");
      toast(`Signed out ${res?.revoked ?? 0} other session(s)`, "success");
      await load();
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Could not revoke sessions", "error");
    } finally {
      setRevoking(false);
    }
  };

  if (loading) return <TabLoading label="Loading active sessions…" />;
  if (error) return <TabError message={error} onRetry={load} />;

  return (
    <Card title={`Active sessions (${sessions.length})`} icon={<IconMonitorSmartphone className="h-4 w-4" />}>
      <p className="mb-4 text-sm text-[var(--vbase-slate500)]">
        Each sign-in creates a server-side session. Revoking others immediately signs those browsers out.
      </p>
      <div className="divide-y divide-[var(--vbase-border)]">
        {sessions.map((s) => (
          <div key={s.id} className="flex items-center gap-3 py-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-[var(--vbase-bg-alt)]">
              <IconMonitorSmartphone className="h-4 w-4 text-[var(--vbase-slate500)]" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="flex items-center gap-2 font-medium text-[var(--vbase-slate800)]">
                {deviceLabel(s.user_agent)}
                {s.current && (
                  <span className="rounded-full bg-[var(--vbase-green)]/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--vbase-green)]">
                    This device
                  </span>
                )}
              </p>
              <p className="text-xs text-[var(--vbase-slate500)]">
                {s.ip_address || "unknown IP"} · started {fmtWhen(s.created_at)} · last seen {fmtWhen(s.last_seen_at)}{" "}
                · expires {fmtWhen(s.expires_at)}
              </p>
            </div>
          </div>
        ))}
        {!sessions.length && <p className="py-6 text-center text-sm text-[var(--vbase-slate500)]">No active sessions.</p>}
      </div>
      <div className="mt-4 flex items-center justify-between border-t border-[var(--vbase-border)] pt-4">
        <p className="text-xs text-[var(--vbase-slate500)]">Expired and revoked session rows are pruned automatically.</p>
        <button
          onClick={revokeOthers}
          disabled={revoking || sessions.length <= 1}
          className="vbase-btn-danger flex items-center gap-1.5"
        >
          {revoking ? <IconLoader2 className="h-4 w-4 animate-spin" /> : <IconX className="h-4 w-4" />}
          <span>Sign out other sessions</span>
        </button>
      </div>
    </Card>
  );
}

function PreferencesTab({ onSaved }: { onSaved: (prefs: Record<string, unknown>) => void }) {
  const [prefs, setPrefs] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const { mode, setMode } = useThemeStore();

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setPrefs(await api.get<Record<string, any>>("/settings/preferences"));
    } catch (e: any) {
      setError(e?.data?.detail || e?.message || "Could not load preferences");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const update = async (key: string, value: unknown) => {
    try {
      const merged = await api.patch<Record<string, unknown>>("/settings/preferences", { [key]: value });
      setPrefs(merged);
      onSaved(merged);
      toast("Preference saved", "success");
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Could not save preference", "error");
    }
  };

  if (loading) return <TabLoading label="Loading preferences…" />;
  if (error) return <TabError message={error} onRetry={load} />;

  return (
    <Card title="Preferences" icon={<IconSettings className="h-4 w-4" />}>
      <Row label="Theme" hint="Applies immediately and is stored on your account.">
        <select
          value={mode}
          onChange={(e) => {
            const next = e.target.value as ThemeMode;
            setMode(next);
            update("theme", next);
          }}
          className="vbase-select w-40"
        >
          <option value="system">System</option>
          <option value="light">Light</option>
          <option value="dark">Dark</option>
        </select>
      </Row>
      <Row label="Results per page" hint="Default page size for tables.">
        <select
          value={prefs?.page_size || 50}
          onChange={(e) => update("page_size", Number(e.target.value))}
          className="vbase-select w-28"
        >
          {[25, 50, 100, 200].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </Row>
      <Row label="Default landing page" hint="Where the app opens after sign-in.">
        <select
          value={prefs?.landing_page || "/dashboard"}
          onChange={(e) => update("landing_page", e.target.value)}
          className="vbase-select w-48"
        >
          <option value="/dashboard">Dashboard</option>
          <option value="/companies">Companies</option>
          <option value="/contacts">Contacts</option>
          <option value="/all-records">All Records</option>
          <option value="/import">Import Center</option>
        </select>
      </Row>
      <Row label="Confirm destructive actions" hint="Ask before deletes, merges and restores.">
        <Toggle
          checked={prefs?.confirm_destructive !== false}
          onChange={(v) => update("confirm_destructive", v)}
        />
      </Row>
    </Card>
  );
}

function UsersTab({ currentUserId }: { currentUserId?: number }) {
  const [rows, setRows] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.get<{ items: UserRow[] }>("/users", { params: { page_size: 100 } });
      setRows(data.items || []);
    } catch (e: any) {
      setError(e?.data?.detail || e?.message || "Could not load users");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (row: UserRow, action: "deactivate" | "restore" | "promote" | "demote") => {
    setBusy(row.id);
    try {
      if (action === "deactivate") await api.post(`/users/${row.id}/deactivate`);
      else if (action === "restore") await api.post(`/users/${row.id}/restore`);
      else await api.patch(`/users/${row.id}`, { is_superuser: action === "promote" });
      toast("User updated", "success");
      await load();
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Update failed", "error");
    } finally {
      setBusy(null);
    }
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.email.toLowerCase().includes(q) ||
        r.username.toLowerCase().includes(q) ||
        (r.full_name || "").toLowerCase().includes(q)
    );
  }, [rows, query]);

  if (loading) return <TabLoading label="Loading users…" />;
  if (error) return <TabError message={error} onRetry={load} />;

  return (
    <Card title={`Users (${rows.length})`} icon={<IconUsers className="h-4 w-4" />}>
      <div className="mb-4 flex items-center gap-3">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search users…"
          className="vbase-input max-w-xs"
        />
        <Link to="/signup" className="vbase-btn-secondary flex items-center gap-1.5">
          <IconUserPlus className="h-4 w-4" />
          <span>Create account</span>
        </Link>
      </div>
      <div className="overflow-x-auto">
        <table className="vbase-table">
          <thead>
            <tr>
              <th>User</th>
              <th>Role</th>
              <th>Status</th>
              <th>Joined</th>
              <th>Last login</th>
              <th className="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => (
              <tr key={row.id}>
                <td>
                  <p className="font-medium text-[var(--vbase-slate800)]">
                    {row.full_name || row.username}
                    {row.id === currentUserId && <span className="ml-2 text-xs text-[var(--vbase-slate400)]">(you)</span>}
                  </p>
                  <p className="text-xs text-[var(--vbase-slate500)]">{row.email}</p>
                </td>
                <td>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      row.is_superuser
                        ? "bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]"
                        : "bg-[var(--vbase-bg-alt)] text-[var(--vbase-slate600)]"
                    }`}
                  >
                    {row.is_superuser ? "Admin" : "Member"}
                  </span>
                </td>
                <td>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      row.is_active
                        ? "bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]"
                        : "bg-[var(--vbase-red)]/10 text-[var(--vbase-red)]"
                    }`}
                  >
                    {row.is_active ? "Active" : "Disabled"}
                  </span>
                </td>
                <td className="text-[var(--vbase-slate500)]">{fmtWhen(row.created_at)}</td>
                <td className="text-[var(--vbase-slate500)]">{fmtWhen(row.last_login_at)}</td>
                <td>
                  <div className="flex items-center justify-end gap-1.5">
                    {busy === row.id ? (
                      <IconLoader2 className="h-4 w-4 animate-spin text-[var(--vbase-slate400)]" />
                    ) : (
                      <>
                        <button
                          onClick={() => act(row, row.is_superuser ? "demote" : "promote")}
                          disabled={row.id === currentUserId}
                          className="vbase-btn-ghost text-xs"
                        >
                          {row.is_superuser ? "Make member" : "Make admin"}
                        </button>
                        <button
                          onClick={() => act(row, row.is_active ? "deactivate" : "restore")}
                          disabled={row.id === currentUserId}
                          className={`vbase-btn text-xs ${row.is_active ? "vbase-btn-danger" : "vbase-btn-secondary"}`}
                        >
                          {row.is_active ? "Disable" : "Restore"}
                        </button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!filtered.length && (
          <p className="py-8 text-center text-sm text-[var(--vbase-slate500)]">No users match this search.</p>
        )}
      </div>
      <p className="mt-4 flex items-start gap-2 border-t border-[var(--vbase-border)] pt-4 text-xs text-[var(--vbase-slate500)]">
        <IconInfo className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
        Imported business data is private by default: every API route requires a session, and all records are scoped to
        the authenticated workspace.
      </p>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Small presentational helpers
// ---------------------------------------------------------------------------

function Card({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="vbase-card p-5">
      <h2 className="mb-4 flex items-center gap-2 font-semibold text-[var(--vbase-slate800)]">
        {icon}
        {title}
      </h2>
      {children}
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-[var(--vbase-border)] py-2.5 last:border-0">
      <span className="text-xs uppercase tracking-wider text-[var(--vbase-slate500)]">{label}</span>
      <span className={`text-right text-sm text-[var(--vbase-slate700)] ${mono ? "font-mono text-[11px]" : ""}`}>
        {value}
      </span>
    </div>
  );
}

function Row({ label, hint, children }: { label: string; hint: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-[var(--vbase-border)] py-3 last:border-0">
      <div>
        <p className="text-sm font-medium text-[var(--vbase-slate800)]">{label}</p>
        <p className="text-xs text-[var(--vbase-slate500)]">{hint}</p>
      </div>
      {children}
    </div>
  );
}

function Bullet({ children, ok }: { children: React.ReactNode; ok?: boolean }) {
  return (
    <li className="flex items-start gap-2">
      {ok ? (
        <IconCheck className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--vbase-green)]" />
      ) : (
        <IconInfo className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--vbase-slate400)]" />
      )}
      <span>{children}</span>
    </li>
  );
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`relative h-6 w-11 flex-shrink-0 rounded-full transition-colors ${
        checked ? "bg-[var(--vbase-indigo)]" : "bg-[var(--vbase-slate300)]"
      }`}
    >
      <span
        className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${
          checked ? "left-[22px]" : "left-0.5"
        }`}
      />
    </button>
  );
}

function TabLoading({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center gap-2 py-16 text-sm text-[var(--vbase-slate500)]">
      <IconLoader2 className="h-6 w-6 animate-spin text-[var(--vbase-indigo)]" />
      {label}
    </div>
  );
}

function TabError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-sm text-[var(--vbase-red)]">
      <IconAlertCircle className="h-6 w-6" />
      {message}
      {onRetry && (
        <button onClick={onRetry} className="vbase-btn-secondary flex items-center gap-1.5">
          <IconRefreshCcw className="h-4 w-4" />
          <span>Retry</span>
        </button>
      )}
    </div>
  );
}
