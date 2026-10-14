import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { IconMailPlus, IconPause, IconPlay, IconX } from "@/lib/icons";
import { api } from "@/lib/api";
import { toast } from "@/lib/store";
import type { EmailSequence, SequenceEnrollment } from "@/lib/types";

/**
 * The contact's place in any sequences, plus the control to put them in one.
 *
 * Enrolling is a decision people make from a record, so it lives here rather
 * than only on the sequences page — the same reason "send email" lives here.
 */
export function ContactSequences({ contactId }: { contactId: number }) {
  const [enrollments, setEnrollments] = useState<SequenceEnrollment[]>([]);
  const [sequences, setSequences] = useState<EmailSequence[]>([]);
  const [selected, setSelected] = useState<number | "">("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [enrollmentList, list] = await Promise.all([
        api.get<{ items: SequenceEnrollment[] }>("/sequences/enrollments", { params: { contact_id: contactId } }),
        api.get<{ items: EmailSequence[] }>("/sequences"),
      ]);
      setEnrollments(enrollmentList.items);
      setSequences(list.items.filter((sequence) => sequence.is_active));
    } catch (e: any) {
      toast(e?.data?.detail || "Could not load sequences", "error");
    } finally {
      setLoading(false);
    }
  }, [contactId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const liveIds = new Set(
    enrollments.filter((e) => e.status === "active" || e.status === "paused").map((e) => e.sequence_id)
  );
  const enrollable = sequences.filter((sequence) => !liveIds.has(sequence.id));

  const enroll = async () => {
    if (selected === "") return;
    setBusy(true);
    try {
      await api.post(`/sequences/${selected}/enroll`, { contact_id: contactId });
      toast("Enrolled in sequence", "success");
      setSelected("");
      refresh();
    } catch (e: any) {
      toast(e?.data?.detail || "Could not enroll this contact", "error");
    } finally {
      setBusy(false);
    }
  };

  const change = async (enrollment: SequenceEnrollment, status: "active" | "paused" | "cancelled") => {
    try {
      await api.patch(`/sequences/enrollments/${enrollment.id}`, { status });
      refresh();
    } catch (e: any) {
      toast(e?.data?.detail || "Could not update enrollment", "error");
    }
  };

  return (
    <div className="flex items-start gap-3 rounded-lg border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] p-4">
      <div className="mt-0.5 flex h-7 w-7 items-center justify-center rounded border border-[var(--vbase-border)] bg-[var(--vbase-bg)] text-[var(--vbase-slate500)]">
        <IconMailPlus className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-[var(--vbase-slate500)]">Sequences</p>
        <div className="mt-1.5">
          {!loading && enrollments.length > 0 && (
            <ul className="mb-2 flex flex-col gap-1.5">
              {enrollments.map((enrollment) => (
                <li key={enrollment.id} className="flex items-center gap-2 text-sm">
                  <Link
                    to="/sequences"
                    className="min-w-0 flex-1 truncate text-[var(--vbase-slate800)] hover:underline"
                    title={enrollment.sequence_name || undefined}
                  >
                    {enrollment.sequence_name || `Sequence #${enrollment.sequence_id}`}
                  </Link>
                  <span className="flex-shrink-0 text-xs text-[var(--vbase-slate500)]">
                    step {enrollment.current_step + 1}
                  </span>
                  <span className="flex-shrink-0 text-xs text-[var(--vbase-slate400)]">
                    {enrollment.status === "active"
                      ? `next ${new Date(enrollment.next_send_at || "").toLocaleDateString()}`
                      : enrollment.status}
                  </span>
                  {(enrollment.status === "active" || enrollment.status === "paused") && (
                    <span className="flex flex-shrink-0 gap-0.5">
                      <button
                        type="button"
                        onClick={() => change(enrollment, enrollment.status === "active" ? "paused" : "active")}
                        aria-label={enrollment.status === "active" ? "Pause sequence" : "Resume sequence"}
                        className="text-[var(--vbase-slate400)] transition-colors hover:text-[var(--vbase-slate700)]"
                      >
                        {enrollment.status === "active" ? (
                          <IconPause className="h-3.5 w-3.5" />
                        ) : (
                          <IconPlay className="h-3.5 w-3.5" />
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() => change(enrollment, "cancelled")}
                        aria-label="Cancel sequence"
                        className="text-[var(--vbase-slate400)] transition-colors hover:text-[var(--vbase-red)]"
                      >
                        <IconX className="h-3.5 w-3.5" />
                      </button>
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}

          {enrollable.length > 0 ? (
            <div className="flex gap-2">
              <select
                value={selected}
                onChange={(e) => setSelected(e.target.value === "" ? "" : Number(e.target.value))}
                aria-label="Sequence to enroll in"
                className="vbase-input h-8 min-w-0 flex-1 text-sm"
              >
                <option value="">Choose a sequence…</option>
                {enrollable.map((sequence) => (
                  <option key={sequence.id} value={sequence.id}>
                    {sequence.name} ({sequence.step_count} step{sequence.step_count === 1 ? "" : "s"})
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={enroll}
                disabled={selected === "" || busy}
                className="vbase-btn-ghost flex-shrink-0 text-sm"
              >
                Enroll
              </button>
            </div>
          ) : (
            !loading && (
              <p className="text-sm text-[var(--vbase-slate400)]">
                {enrollments.length
                  ? "In every active sequence."
                  : "No sequences yet. Create one to send follow-ups on a schedule."}
              </p>
            )
          )}
        </div>
      </div>
    </div>
  );
}
