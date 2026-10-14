import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  IconClock,
  IconEdit,
  IconEyeIcon,
  IconMail,
  IconPause,
  IconPlay,
  IconPlus,
  IconSend,
  IconTrash2,
  IconX,
} from "@/lib/icons";
import { api } from "@/lib/api";
import { EmptyState } from "@/components/crm";
import { toast } from "@/lib/store";
import type { EmailSequence, SequenceEnrollment, SequenceStep } from "@/lib/types";

const STATUS_LABEL: Record<SequenceEnrollment["status"], string> = {
  active: "Active",
  paused: "Paused",
  completed: "Done",
  cancelled: "Cancelled",
  failed: "Failed",
};

function formatWhen(iso?: string | null): string {
  if (!iso) return "—";
  const value = new Date(iso);
  if (Number.isNaN(value.getTime())) return "—";
  const diffMs = value.getTime() - Date.now();
  const days = Math.round(diffMs / 86_400_000);
  if (Math.abs(diffMs) < 3_600_000) return diffMs >= 0 ? "in a few minutes" : "just now";
  if (Math.abs(days) < 1) return value.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return value.toLocaleDateString([], { month: "short", day: "numeric" }) + (diffMs < 0 ? "" : "");
}

export function SequencesPage() {
  const [sequences, setSequences] = useState<EmailSequence[]>([]);
  const [variables, setVariables] = useState<string[]>([]);
  const [enrollments, setEnrollments] = useState<SequenceEnrollment[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<EmailSequence | null>(null);
  const [creating, setCreating] = useState(false);
  const [previewing, setPreviewing] = useState<EmailSequence | null>(null);
  const [dispatching, setDispatching] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [list, enrollmentList] = await Promise.all([
        api.get<{ items: EmailSequence[]; variables: string[] }>("/sequences"),
        api.get<{ items: SequenceEnrollment[] }>("/sequences/enrollments", { params: { limit: 60 } }),
      ]);
      setSequences(list.items);
      setVariables(list.variables);
      setEnrollments(enrollmentList.items);
    } catch (e: any) {
      toast(e?.data?.detail || "Could not load sequences", "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  const sendDue = async () => {
    setDispatching(true);
    try {
      const outcome = await api.post<{ sent: number; failed: number; completed: number; skipped?: string }>(
        "/sequences/dispatch"
      );
      if (outcome.skipped === "not_configured") {
        toast("Email is not configured yet, so nothing was sent", "info");
      } else {
        toast(`Sent ${outcome.sent} email${outcome.sent === 1 ? "" : "s"}`, "success");
      }
      await fetchAll();
    } catch (e: any) {
      toast(e?.data?.detail || "Could not send due emails", "error");
    } finally {
      setDispatching(false);
    }
  };

  const setPaused = async (sequence: EmailSequence) => {
    try {
      await api.patch(`/sequences/${sequence.id}`, { is_active: !sequence.is_active });
      fetchAll();
    } catch (e: any) {
      toast(e?.data?.detail || "Could not update sequence", "error");
    }
  };

  const remove = async (sequence: EmailSequence) => {
    const people = sequence.active_enrollments;
    const warning = people
      ? `“${sequence.name}” has ${people} contact${people === 1 ? "" : "s"} still moving through it. Delete anyway?`
      : `Delete sequence “${sequence.name}”?`;
    if (!window.confirm(warning)) return;
    try {
      await api.delete(`/sequences/${sequence.id}`);
      toast("Sequence deleted", "success");
      fetchAll();
    } catch (e: any) {
      toast(e?.data?.detail || "Could not delete sequence", "error");
    }
  };

  const totals = useMemo(() => {
    const live = sequences.filter((s) => s.is_active).length;
    const inFlight = enrollments.filter((e) => e.status === "active" || e.status === "paused").length;
    const sent = sequences.reduce((sum, s) => sum + s.emails_sent, 0);
    return { live, inFlight, sent };
  }, [sequences, enrollments]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Email sequences</h1>
          <p className="mt-0.5 text-sm text-[var(--vbase-slate500)]">
            {totals.live} running · {totals.inFlight} contacts in flight · {totals.sent} emails sent.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={sendDue} disabled={dispatching} className="vbase-btn-ghost flex items-center gap-1.5">
            <IconSend className="h-4 w-4" />
            <span>{dispatching ? "Sending…" : "Send due now"}</span>
          </button>
          <button onClick={() => setCreating(true)} className="vbase-btn-primary flex items-center gap-1.5">
            <IconPlus className="h-4 w-4" />
            <span>New sequence</span>
          </button>
        </div>
      </div>

      {(creating || editing) && (
        <SequenceEditor
          sequence={editing}
          variables={variables}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
          onSaved={() => {
            setCreating(false);
            setEditing(null);
            fetchAll();
          }}
        />
      )}

      {previewing && <SequencePreview sequence={previewing} onClose={() => setPreviewing(null)} />}

      <div className="grid gap-3">
        {sequences.length === 0 && !loading ? (
          <div className="vbase-card">
            <EmptyState
              icon="task"
              title="No sequences yet"
              description="A sequence is a few follow-ups written once and sent on a schedule, so the second and third touch happen without anyone remembering to send them."
              actionLabel="New sequence"
              onAction={() => setCreating(true)}
            />
          </div>
        ) : (
          sequences.map((sequence) => (
            <div key={sequence.id} className="vbase-card flex flex-wrap items-start gap-4 p-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-sm font-semibold text-[var(--vbase-slate900)]">{sequence.name}</h2>
                  <span
                    className={`rounded-full border px-2 py-0.5 text-xs font-medium ${
                      sequence.is_active
                        ? "border-[var(--vbase-green)]/30 bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]"
                        : "border-[var(--vbase-border)] text-[var(--vbase-slate500)]"
                    }`}
                  >
                    {sequence.is_active ? "Running" : "Paused"}
                  </span>
                  {sequence.failed_enrollments > 0 && (
                    <span className="rounded-full border border-[var(--vbase-red)]/30 bg-[var(--vbase-red)]/10 px-2 py-0.5 text-xs font-medium text-[var(--vbase-red)]">
                      {sequence.failed_enrollments} failed
                    </span>
                  )}
                </div>
                {sequence.description && (
                  <p className="mt-1 text-sm text-[var(--vbase-slate500)]">{sequence.description}</p>
                )}
                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--vbase-slate500)]">
                  <span className="inline-flex items-center gap-1">
                    <IconMail className="h-3.5 w-3.5" />
                    {sequence.step_count} step{sequence.step_count === 1 ? "" : "s"}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <IconClock className="h-3.5 w-3.5" />
                    {sequence.active_enrollments} in flight · {sequence.completed_enrollments} done
                  </span>
                  <span>{sequence.emails_sent} sent</span>
                </div>
              </div>

              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setPreviewing(sequence)}
                  className="vbase-btn-ghost flex items-center gap-1.5 text-sm"
                  title="Preview the rendered steps"
                >
                  <IconEyeIcon className="h-4 w-4" />
                  Preview
                </button>
                <button
                  onClick={() => setPaused(sequence)}
                  className="vbase-btn-ghost flex items-center gap-1.5 text-sm"
                  title={sequence.is_active ? "Pause every enrollment in this sequence" : "Resume sending"}
                >
                  {sequence.is_active ? <IconPause className="h-4 w-4" /> : <IconPlay className="h-4 w-4" />}
                  {sequence.is_active ? "Pause" : "Resume"}
                </button>
                <button
                  onClick={() => setEditing(sequence)}
                  className="vbase-btn-ghost flex items-center gap-1.5 text-sm"
                >
                  <IconEdit className="h-4 w-4" />
                  Edit
                </button>
                <button
                  onClick={() => remove(sequence)}
                  className="vbase-btn-ghost flex items-center gap-1.5 text-sm text-[var(--vbase-red)]"
                >
                  <IconTrash2 className="h-4 w-4" />
                  Delete
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold text-[var(--vbase-slate900)]">Enrollments</h2>
        <div className="vbase-card overflow-hidden">
          {enrollments.length === 0 ? (
            <p className="px-4 py-6 text-sm text-[var(--vbase-slate500)]">
              Nobody is enrolled yet. Open a contact and choose a sequence to put them in one.
            </p>
          ) : (
            <ul className="divide-y divide-[var(--vbase-border)]">
              {enrollments.map((enrollment) => (
                <li key={enrollment.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      {enrollment.contact_id ? (
                        <Link
                          to={`/contacts/${enrollment.contact_id}`}
                          className="text-sm font-medium text-[var(--vbase-slate900)] hover:underline"
                        >
                          {enrollment.contact_name || `Contact #${enrollment.contact_id}`}
                        </Link>
                      ) : (
                        <span className="text-sm font-medium text-[var(--vbase-slate900)]">
                          {enrollment.contact_name || "Contact"}
                        </span>
                      )}
                      <span className="text-xs text-[var(--vbase-slate500)]">{enrollment.sequence_name}</span>
                      <span
                        className={`rounded-full border px-2 py-0.5 text-xs font-medium ${statusClass(
                          enrollment.status
                        )}`}
                      >
                        {STATUS_LABEL[enrollment.status]}
                      </span>
                    </div>
                    <p className="mt-0.5 truncate text-xs text-[var(--vbase-slate500)]">
                      {enrollment.contact_email || "no email"} · step {enrollment.current_step + 1} · next{" "}
                      {formatWhen(enrollment.next_send_at)}
                      {enrollment.last_error ? ` · ${enrollment.last_error}` : ""}
                    </p>
                  </div>
                  <EnrollmentActions enrollment={enrollment} onChanged={fetchAll} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function statusClass(status: SequenceEnrollment["status"]): string {
  if (status === "active") return "border-[var(--vbase-green)]/30 bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]";
  if (status === "failed") return "border-[var(--vbase-red)]/30 bg-[var(--vbase-red)]/10 text-[var(--vbase-red)]";
  if (status === "paused") return "border-[var(--vbase-amber)]/30 bg-[var(--vbase-amber)]/10 text-[var(--vbase-amber)]";
  return "border-[var(--vbase-border)] text-[var(--vbase-slate500)]";
}

function EnrollmentActions({
  enrollment,
  onChanged,
}: {
  enrollment: SequenceEnrollment;
  onChanged: () => void;
}) {
  const change = async (status: "active" | "paused" | "cancelled") => {
    try {
      await api.patch(`/sequences/enrollments/${enrollment.id}`, { status });
      onChanged();
    } catch (e: any) {
      toast(e?.data?.detail || "Could not update enrollment", "error");
    }
  };

  return (
    <div className="flex items-center gap-1.5">
      {enrollment.status === "active" && (
        <button onClick={() => change("paused")} className="vbase-btn-ghost text-sm">
          <IconPause className="h-4 w-4" />
        </button>
      )}
      {enrollment.status === "paused" && (
        <button onClick={() => change("active")} className="vbase-btn-ghost text-sm">
          <IconPlay className="h-4 w-4" />
        </button>
      )}
      {(enrollment.status === "active" || enrollment.status === "paused") && (
        <button onClick={() => change("cancelled")} className="vbase-btn-ghost text-sm text-[var(--vbase-red)]">
          <IconX className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

function SequenceEditor({
  sequence,
  variables,
  onClose,
  onSaved,
}: {
  sequence: EmailSequence | null;
  variables: string[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(sequence?.name || "");
  const [description, setDescription] = useState(sequence?.description || "");
  const [steps, setSteps] = useState<SequenceStep[]>(
    sequence?.steps.length
      ? sequence.steps.map((step, index) => ({ ...step, position: index }))
      : [{ position: 0, delay_days: 0, subject: "", body: "" }]
  );
  const [saving, setSaving] = useState(false);

  const update = (index: number, patch: Partial<SequenceStep>) =>
    setSteps((current) => current.map((step, i) => (i === index ? { ...step, ...patch } : step)));

  const addStep = () =>
    setSteps((current) => [
      ...current,
      // Suggested gap: the last step's delay is usually a sensible starting point.
      { position: current.length, delay_days: current[current.length - 1]?.delay_days ?? 3, subject: "", body: "" },
    ]);

  const removeStep = (index: number) =>
    setSteps((current) => current.filter((_, i) => i !== index));

  const save = async () => {
    if (!name.trim()) {
      toast("Give the sequence a name", "error");
      return;
    }
    if (steps.some((step) => !step.subject.trim() || !step.body.trim())) {
      toast("Every step needs a subject and a body", "error");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        name: name.trim(),
        description: description.trim() || null,
        steps: steps.map((step, index) => ({
          position: index,
          delay_days: Number(step.delay_days) || 0,
          subject: step.subject.trim(),
          body: step.body,
        })),
      };
      if (sequence) await api.patch(`/sequences/${sequence.id}`, payload);
      else await api.post("/sequences", payload);
      toast(sequence ? "Sequence updated" : "Sequence created", "success");
      onSaved();
    } catch (e: any) {
      toast(e?.data?.detail || "Could not save the sequence", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="vbase-card flex flex-col gap-3 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[var(--vbase-slate900)]">
          {sequence ? "Edit sequence" : "New sequence"}
        </h2>
        <button onClick={onClose} className="vbase-btn-ghost text-sm">
          <IconX className="h-4 w-4" />
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-[var(--vbase-slate500)]">Name</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Post-demo follow-up"
            className="vbase-input h-9"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-[var(--vbase-slate500)]">Description</span>
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What this sequence is for"
            className="vbase-input h-9"
          />
        </label>
      </div>

      <div className="rounded-md border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-3 py-2 text-xs text-[var(--vbase-slate500)]">
        Merge fields:{" "}
        {variables.map((variable) => (
          <code key={variable} className="mr-1.5 rounded bg-[var(--vbase-bg)] px-1 py-0.5">
            {`{{${variable}}}`}
          </code>
        ))}
      </div>

      <ol className="flex flex-col gap-3">
        {steps.map((step, index) => (
          <li key={index} className="rounded-md border border-[var(--vbase-border)] p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-semibold text-[var(--vbase-slate500)]">Step {index + 1}</span>
              <div className="flex items-center gap-2">
                <label className="flex items-center gap-1 text-xs text-[var(--vbase-slate500)]">
                  wait
                  <input
                    type="number"
                    min={0}
                    max={365}
                    value={step.delay_days}
                    onChange={(e) => update(index, { delay_days: Math.max(0, Number(e.target.value) || 0) })}
                    className="vbase-input h-7 w-16 text-right"
                  />
                  days
                </label>
                {steps.length > 1 && (
                  <button onClick={() => removeStep(index)} className="vbase-btn-ghost text-sm text-[var(--vbase-red)]">
                    <IconTrash2 className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>
            <input
              value={step.subject}
              onChange={(e) => update(index, { subject: e.target.value })}
              placeholder="Subject"
              className="vbase-input mb-2 h-9"
            />
            <textarea
              value={step.body}
              onChange={(e) => update(index, { body: e.target.value })}
              placeholder={`Hi {{first_name}},\n\n…`}
              rows={4}
              className="vbase-input resize-y"
            />
          </li>
        ))}
      </ol>

      <div className="flex items-center justify-between">
        <button
          onClick={addStep}
          disabled={steps.length >= 25}
          className="vbase-btn-ghost flex items-center gap-1.5 text-sm"
        >
          <IconPlus className="h-4 w-4" />
          Add step
        </button>
        <button onClick={save} disabled={saving} className="vbase-btn-primary flex items-center gap-1.5 text-sm">
          <IconSend className="h-4 w-4" />
          {saving ? "Saving…" : sequence ? "Save changes" : "Create sequence"}
        </button>
      </div>
    </div>
  );
}

function SequencePreview({ sequence, onClose }: { sequence: EmailSequence; onClose: () => void }) {
  const [contacts, setContacts] = useState<{ id: number; display_name?: string; email?: string | null }[]>([]);
  const [contactId, setContactId] = useState<number | "">("");
  const [steps, setSteps] = useState<{ position: number; delay_days: number; subject: string; body: string }[] | null>(
    null
  );
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api
      .get<{ items: { id: number; display_name?: string; email?: string | null }[] }>("/contacts", {
        params: { page_size: 50 },
      })
      .then((data) => setContacts(data.items))
      .catch(() => toast("Could not load contacts for preview", "error"));
  }, []);

  useEffect(() => {
    if (contactId === "") {
      setSteps(null);
      return;
    }
    setLoading(true);
    api
      .post<{ steps: { position: number; delay_days: number; subject: string; body: string }[] }>(
        `/sequences/${sequence.id}/preview`,
        { contact_id: contactId }
      )
      .then((data) => setSteps(data.steps))
      .catch((e: any) => toast(e?.data?.detail || "Preview failed", "error"))
      .finally(() => setLoading(false));
  }, [contactId, sequence.id]);

  return (
    <div className="vbase-card flex flex-col gap-3 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[var(--vbase-slate900)]">Preview — {sequence.name}</h2>
        <button onClick={onClose} className="vbase-btn-ghost text-sm">
          <IconX className="h-4 w-4" />
        </button>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <span className="text-[var(--vbase-slate500)]">Render as</span>
        <select
          value={contactId}
          onChange={(e) => setContactId(e.target.value === "" ? "" : Number(e.target.value))}
          className="vbase-input h-9 max-w-sm"
        >
          <option value="">Choose a contact…</option>
          {contacts.map((contact) => (
            <option key={contact.id} value={contact.id}>
              {contact.display_name || `Contact #${contact.id}`}
            </option>
          ))}
        </select>
      </label>

      {contactId !== "" && (
        <div className="flex flex-col gap-3">
          {loading && <p className="text-sm text-[var(--vbase-slate500)]">Rendering…</p>}
          {steps?.map((step) => (
            <article key={step.position} className="rounded-md border border-[var(--vbase-border)] p-3">
              <p className="text-xs text-[var(--vbase-slate500)]">
                Step {step.position + 1} · day {step.delay_days}
              </p>
              <p className="mt-1 text-sm font-semibold text-[var(--vbase-slate900)]">{step.subject}</p>
              <p className="mt-1 whitespace-pre-wrap text-sm text-[var(--vbase-slate700)]">{step.body}</p>
            </article>
          ))}
          {steps && steps.length === 0 && (
            <p className="text-sm text-[var(--vbase-slate500)]">This sequence has no steps yet.</p>
          )}
        </div>
      )}
    </div>
  );
}
