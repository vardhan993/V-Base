import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { toast } from "@/lib/store";
import {
  IconAlertCircle,
  IconCheck,
  IconLoader2,
  IconMail,
  IconSend,
  IconX,
} from "@/lib/icons";

// ---------------------------------------------------------------------------
// Contract mirrored from backend/src/nexus/api/v1/email.py
// ---------------------------------------------------------------------------

export interface EmailStatus {
  configured: boolean;
  provider: string;
  supported_providers: string[];
  from_email: string | null;
  from_name: string | null;
  reply_to: string | null;
  credential_source: "environment" | "settings" | "none";
  missing: string[];
  default_provider: string;
  env_vars: string[];
  gmail_env_vars: string[];
  setting_keys: string[];
  /** Present only while the Gmail provider is selected. */
  gmail_connect_url: string | null;
  gmail_connected: boolean;
  /** Where the provider should post delivery events. */
  webhook_path: string;
  webhook_configured: boolean;
}

export interface SentEmail {
  id: number;
  to?: string | null;
  subject?: string | null;
  provider?: string | null;
  message_id?: string | null;
  from?: string | null;
  preview?: string | null;
  /** Delivery state, updated by the provider's webhook. */
  status?: string | null;
  last_event_at?: string | null;
  sent_at?: string | null;
  user_id?: number | null;
}

/** Tone per delivery status, so a bounce is never mistaken for a delivery. */
const STATUS_TONE: Record<string, string> = {
  sent: "border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] text-[var(--vbase-slate600)]",
  delivered: "border-[var(--vbase-green)]/30 bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]",
  opened: "border-[var(--vbase-indigo)]/30 bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]",
  clicked: "border-[var(--vbase-indigo)]/30 bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]",
  delivery_delayed: "border-[var(--vbase-amber)]/30 bg-[var(--vbase-amber)]/10 text-[var(--vbase-amber)]",
  bounced: "border-[var(--vbase-red)]/30 bg-[var(--vbase-red)]/10 text-[var(--vbase-red)]",
  complained: "border-[var(--vbase-red)]/30 bg-[var(--vbase-red)]/10 text-[var(--vbase-red)]",
  failed: "border-[var(--vbase-red)]/30 bg-[var(--vbase-red)]/10 text-[var(--vbase-red)]",
};

function DeliveryStatus({ status }: { status?: string | null }) {
  const label = status || "sent";
  const tone = STATUS_TONE[label] ?? STATUS_TONE.sent;
  return (
    <span
      className={`inline-flex flex-shrink-0 items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${tone}`}
      title={`Delivery status: ${label}`}
    >
      {label.replace(/_/g, " ")}
    </span>
  );
}

/** Where to create a provider key, per supported provider. */
const PROVIDER_KEYS_URL: Record<string, string> = {
  resend: "https://resend.com/api-keys",
};

export const PROVIDER_LABELS: Record<string, string> = {
  resend: "Resend",
  gmail: "Gmail (Google Workspace)",
};

function firstName(name?: string | null) {
  return (name || "").trim().split(/\s+/)[0] || "there";
}

/** Pre-filled subject/body so a follow-up is one edit away from ready. */
function defaultDraft(name?: string | null) {
  return {
    subject: "Following up",
    body: `Hi ${firstName(name)},\n\nI wanted to follow up on our conversation.\n\nBest regards,\n`,
  };
}

// ---------------------------------------------------------------------------
// Composer
// ---------------------------------------------------------------------------

export function EmailComposer({
  open,
  to,
  name,
  contactId,
  onClose,
  onSent,
}: {
  open: boolean;
  to?: string | null;
  name?: string | null;
  contactId?: number;
  onClose: () => void;
  onSent?: () => void;
}) {
  const [status, setStatus] = useState<EmailStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [draft, setDraft] = useState(() => defaultDraft(name));
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setError("");
    setDraft(defaultDraft(name));
  }, [open, name, to]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoadingStatus(true);
    api
      .get<EmailStatus>("/email/status")
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => {
        if (!cancelled) setStatus(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingStatus(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const send = async () => {
    if (!to) {
      setError("This contact has no email address.");
      return;
    }
    if (!draft.subject.trim() || !draft.body.trim()) {
      setError("A subject and a message are both required.");
      return;
    }
    setSending(true);
    setError("");
    try {
      await api.post("/email/send", {
        to,
        subject: draft.subject.trim(),
        text: draft.body,
        contact_id: contactId,
      });
      toast(`Email sent to ${to}`, "success");
      onSent?.();
      onClose();
    } catch (e: any) {
      setError(e instanceof ApiError ? e.message : e?.data?.detail || e?.message || "Could not send the email");
    } finally {
      setSending(false);
    }
  };

  if (!open) return null;

  const configured = status?.configured ?? false;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 pt-[8vh]">
      <div className="w-full max-w-xl rounded-xl border border-[var(--vbase-border)] bg-[var(--vbase-bg)] shadow-xl">
        <div className="flex items-center justify-between border-b border-[var(--vbase-border)] px-5 py-3">
          <h3 className="flex items-center gap-2 font-semibold text-[var(--vbase-slate900)]">
            <IconMail className="h-4 w-4 text-[var(--vbase-indigo)]" />
            Send email
          </h3>
          <button
            onClick={onClose}
            aria-label="Close"
            className="vbase-btn-ghost vbase-btn-icon-sm"
          >
            <IconX className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-3 px-5 py-4">
          {loadingStatus ? (
            <p className="flex items-center gap-2 text-sm text-[var(--vbase-slate500)]">
              <IconLoader2 className="h-4 w-4 animate-spin" />
              Checking email configuration…
            </p>
          ) : !configured ? (
            <EmailSetupHint status={status} />
          ) : (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block">
                  <span className="text-xs uppercase tracking-wider text-[var(--vbase-slate500)]">To</span>
                  <input value={to || ""} readOnly className="vbase-input mt-1 bg-[var(--vbase-bg-alt)]" />
                </label>
                <label className="block">
                  <span className="text-xs uppercase tracking-wider text-[var(--vbase-slate500)]">From</span>
                  <input
                    value={status?.from_email || ""}
                    readOnly
                    className="vbase-input mt-1 bg-[var(--vbase-bg-alt)]"
                  />
                </label>
              </div>

              <label className="block">
                <span className="text-xs uppercase tracking-wider text-[var(--vbase-slate500)]">Subject</span>
                <input
                  value={draft.subject}
                  onChange={(e) => setDraft((d) => ({ ...d, subject: e.target.value }))}
                  className="vbase-input mt-1"
                  placeholder="What is this about?"
                />
              </label>

              <label className="block">
                <span className="text-xs uppercase tracking-wider text-[var(--vbase-slate500)]">Message</span>
                <textarea
                  value={draft.body}
                  onChange={(e) => setDraft((d) => ({ ...d, body: e.target.value }))}
                  rows={10}
                  className="vbase-input mt-1 h-auto resize-y py-2 leading-relaxed"
                  placeholder="Write your message…"
                />
              </label>

              <p className="text-xs text-[var(--vbase-slate500)]">
                Sent through <span className="font-medium">{status?.provider}</span> and recorded on this record's
                timeline.
              </p>
            </>
          )}

          {error && (
            <p className="flex items-start gap-2 rounded-md border border-[var(--vbase-red)]/30 bg-[var(--vbase-red)]/5 px-3 py-2 text-xs text-[var(--vbase-red)]">
              <IconAlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
              <span>{error}</span>
            </p>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-[var(--vbase-border)] px-5 py-3">
          <button onClick={onClose} className="vbase-btn-ghost">
            Cancel
          </button>
          <button
            onClick={send}
            disabled={sending || !configured || !to}
            className="vbase-btn-primary flex items-center gap-1.5"
          >
            {sending ? <IconLoader2 className="h-4 w-4 animate-spin" /> : <IconSend className="h-4 w-4" />}
            <span>{sending ? "Sending…" : "Send email"}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

/** Shown instead of the form when the selected provider is not usable yet. */
function EmailSetupHint({ status }: { status: EmailStatus | null }) {
  const provider = status?.provider || status?.default_provider || "resend";
  const keyUrl = PROVIDER_KEYS_URL[provider];
  const missing = status?.missing ?? [];
  return (
    <div className="space-y-3 text-sm">
      <p className="flex items-start gap-2 rounded-md border border-[var(--vbase-amber)]/30 bg-[var(--vbase-amber)]/5 px-3 py-2 text-xs text-[var(--vbase-slate700)]">
        <IconAlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-[var(--vbase-amber)]" />
        <span>
          Email sending is not configured yet
          {missing.length ? ` — still needed: ${missing.join(", ")}` : ""}.
        </span>
      </p>

      {provider === "gmail" ? (
        <ol className="list-decimal space-y-1.5 pl-5 text-xs leading-relaxed text-[var(--vbase-slate600)]">
          <li>
            In Google Cloud, create an OAuth client of type <em>Web application</em>, enable the Gmail API, and add
            this authorised redirect URI:{" "}
            <code className="break-all font-mono">&lt;your API origin&gt;/api/v1/email/gmail/callback</code>.
          </li>
          <li>
            Set <code className="font-mono">GMAIL_CLIENT_ID</code> and{" "}
            <code className="font-mono">GMAIL_CLIENT_SECRET</code> in the API environment (or as settings keys) and
            restart it.
          </li>
          <li>
            Then open Settings → General and press <strong>Connect Gmail</strong> to authorise the mailbox. V-Base
            requests the send-only scope; it cannot read your mail.
          </li>
        </ol>
      ) : (
        <ol className="list-decimal space-y-1.5 pl-5 text-xs leading-relaxed text-[var(--vbase-slate600)]">
          <li>
            Create a provider account and an API key
            {keyUrl && (
              <>
                {" "}
                at{" "}
                <a
                  href={keyUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-[var(--vbase-indigo)] hover:underline"
                >
                  {keyUrl.replace("https://", "")}
                </a>
              </>
            )}
            . The free tier covers a normal follow-up volume.
          </li>
          <li>
            Verify the sending domain, then set <code className="font-mono">EMAIL_API_KEY</code> and{" "}
            <code className="font-mono">EMAIL_FROM</code> in the API environment and restart it.
          </li>
          <li>
            Alternatively store <code className="font-mono">{status?.setting_keys?.join(", ") || "email_api_key"}</code>{" "}
            from Settings → General, which needs no restart.
          </li>
        </ol>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sent history
// ---------------------------------------------------------------------------

export function SentEmails({ contactId }: { contactId: number }) {
  const [items, setItems] = useState<SentEmail[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await api.get<{ items: SentEmail[] }>("/email/messages", {
        params: { contact_id: contactId, limit: 10 },
      });
      setItems(data.items);
    } catch {
      /* history is secondary — the record still renders */
    } finally {
      setLoading(false);
    }
  }, [contactId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-[var(--vbase-slate500)]">
        <IconLoader2 className="h-4 w-4 animate-spin" />
        Loading email history…
      </div>
    );
  }

  if (!items.length) {
    return (
      <p className="text-sm text-[var(--vbase-slate500)]">
        No emails sent from V-Base yet. Use <span className="font-medium">Send email</span> to start a thread.
      </p>
    );
  }

  return (
    <ul className="space-y-3">
      {items.map((m) => (
        <li key={m.id} className="border-b border-[var(--vbase-border)] pb-3 last:border-0 last:pb-0">
          <div className="flex items-start justify-between gap-2">
            <p className="flex min-w-0 items-center gap-2 text-sm font-medium text-[var(--vbase-slate800)]">
              <IconCheck className="h-3.5 w-3.5 flex-shrink-0 text-[var(--vbase-green)]" />
              <span className="truncate">{m.subject || "(no subject)"}</span>
            </p>
            <DeliveryStatus status={m.status} />
          </div>
          <p className="mt-0.5 truncate text-xs text-[var(--vbase-slate500)]" title={m.preview || undefined}>
            To {m.to} · {m.provider} · {m.sent_at ? new Date(m.sent_at).toLocaleString() : "—"}
          </p>
        </li>
      ))}
    </ul>
  );
}
