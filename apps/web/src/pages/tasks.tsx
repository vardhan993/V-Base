import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { IconPlus, IconCheck, IconTrash2, IconClock, IconCalendarDays, IconX } from "@/lib/icons";
import { api } from "@/lib/api";
import { ContactAvatar, EmptyState } from "@/components/crm";
import { toast } from "@/lib/store";

interface TaskItem {
  id: number;
  title: string;
  notes?: string | null;
  contact_id?: number | null;
  company_id?: number | null;
  contact_name?: string | null;
  company_name?: string | null;
  due_at?: string | null;
  done: boolean;
  overdue: boolean;
  created_at?: string | null;
}

export function TasksPage() {
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [total, setTotal] = useState(0);
  const [openCount, setOpenCount] = useState(0);
  const [filter, setFilter] = useState<"open" | "done" | "overdue" | "all">("open");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page_size: 100 };
      if (filter === "open") params.done = false;
      else if (filter === "done") params.done = true;
      else if (filter === "overdue") params.overdue = true;
      if (query.trim()) params.q = query.trim();
      const data = await api.get<{ items: TaskItem[]; total: number; open_count: number }>("/tasks", { params: params as any });
      setTasks(data.items);
      setTotal(data.total);
      setOpenCount(data.open_count);
    } catch (e: any) {
      toast(e?.data?.detail || "Could not load tasks", "error");
    } finally {
      setLoading(false);
    }
  }, [filter, query]);

  useEffect(() => {
    const t = window.setTimeout(fetchTasks, query ? 300 : 0);
    return () => window.clearTimeout(t);
  }, [fetchTasks, query]);

  const toggle = async (task: TaskItem) => {
    try {
      await api.patch(`/tasks/${task.id}`, { done: !task.done });
      fetchTasks();
    } catch (e: any) {
      toast(e?.data?.detail || "Could not update task", "error");
    }
  };

  const remove = async (task: TaskItem) => {
    if (!window.confirm(`Delete task “${task.title}”?`)) return;
    try {
      await api.delete(`/tasks/${task.id}`);
      toast("Task deleted", "success");
      fetchTasks();
    } catch (e: any) {
      toast(e?.data?.detail || "Could not delete task", "error");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Follow-ups</h1>
          <p className="mt-0.5 text-sm text-[var(--vbase-slate500)]">
            {openCount} open · never lose track of the next call, email, or demo.
          </p>
        </div>
        <button onClick={() => setCreateOpen(true)} className="vbase-btn-primary flex items-center gap-1.5">
          <IconPlus className="h-4 w-4" />
          <span>New task</span>
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {(["open", "overdue", "done", "all"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              filter === f
                ? "bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]"
                : "text-[var(--vbase-slate500)] hover:bg-[var(--vbase-bg-alt)] hover:text-[var(--vbase-slate700)]"
            }`}
          >
            {f === "open" ? "Open" : f === "overdue" ? "Overdue" : f === "done" ? "Done" : "All"}
          </button>
        ))}
        <div className="relative ml-auto w-full max-w-xs">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search tasks…"
            className="vbase-input h-9 pl-3"
          />
        </div>
      </div>

      {createOpen && <TaskCreateForm onClose={() => setCreateOpen(false)} onCreated={() => { setCreateOpen(false); fetchTasks(); }} />}

      <div className="vbase-card overflow-hidden">
        {tasks.length === 0 && !loading ? (
          <EmptyState
            icon="task"
            title={filter === "done" ? "No completed tasks" : "No follow-ups"}
            description={filter === "done" ? "Completed tasks will appear here." : "Create the first follow-up so nothing slips through."}
            actionLabel="New task"
            onAction={() => setCreateOpen(true)}
          />
        ) : (
          <ul className="divide-y divide-[var(--vbase-border)]">
            {tasks.map((task) => (
              <li key={task.id} className="flex items-start gap-3 px-4 py-3">
                <button
                  onClick={() => toggle(task)}
                  aria-label={task.done ? `Reopen ${task.title}` : `Complete ${task.title}`}
                  title={task.done ? "Reopen" : "Mark done"}
                  className={`mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full border transition-colors ${
                    task.done
                      ? "border-[var(--vbase-green)] bg-[var(--vbase-green)] text-white"
                      : "border-[var(--vbase-border)] text-transparent hover:border-[var(--vbase-green)]"
                  }`}
                >
                  <IconCheck className="h-3 w-3" />
                </button>
                <div className="min-w-0 flex-1">
                  <p className={`truncate text-sm font-medium ${task.done ? "text-[var(--vbase-slate400)] line-through" : "text-[var(--vbase-slate900)]"}`} title={task.title}>
                    {task.title}
                  </p>
                  <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--vbase-slate500)]">
                    {task.due_at && (
                      <span className={`inline-flex items-center gap-1 ${task.overdue ? "font-medium text-[var(--vbase-red)]" : ""}`}>
                        <IconCalendarDays className="h-3 w-3" />
                        {new Date(task.due_at).toLocaleString()}
                        {task.overdue && " · overdue"}
                      </span>
                    )}
                    {task.contact_name && (
                      <Link to={`/contacts/${task.contact_id}`} className="inline-flex min-w-0 items-center gap-1 text-[var(--vbase-indigo)] hover:underline">
                        <ContactAvatar name={task.contact_name} size={18} />
                        <span className="block max-w-[160px] truncate">{task.contact_name}</span>
                      </Link>
                    )}
                    {task.company_name && (
                      <Link to={`/companies/${task.company_id}`} className="block max-w-[160px] truncate text-[var(--vbase-indigo)] hover:underline">
                        {task.company_name}
                      </Link>
                    )}
                  </div>
                  {task.notes && <p className="mt-1 line-clamp-2 text-xs text-[var(--vbase-slate600)]">{task.notes}</p>}
                </div>
                <button
                  onClick={() => remove(task)}
                  aria-label={`Delete ${task.title}`}
                  title="Delete task"
                  className="vbase-btn vbase-btn-icon-sm vbase-btn-danger-soft flex-shrink-0"
                >
                  <IconTrash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
        {total > tasks.length && (
          <p className="border-t border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-4 py-2 text-xs text-[var(--vbase-slate500)]">
            Showing {tasks.length} of {total} — refine the filter to see more.
          </p>
        )}
      </div>
    </div>
  );
}

function TaskCreateForm({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [contactId, setContactId] = useState("");
  const [companyId, setCompanyId] = useState("");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!title.trim()) {
      toast("Give the task a title", "error");
      return;
    }
    setSaving(true);
    try {
      await api.post("/tasks", {
        title: title.trim(),
        notes: notes.trim() || undefined,
        due_at: dueAt ? new Date(dueAt).toISOString() : undefined,
        contact_id: contactId.trim() ? Number(contactId) : undefined,
        company_id: companyId.trim() ? Number(companyId) : undefined,
      });
      toast("Task created", "success");
      onCreated();
    } catch (e: any) {
      toast(e?.data?.detail || "Could not create task", "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="vbase-card p-5">
      <h3 className="flex items-center gap-2 font-semibold text-[var(--vbase-slate800)]">
        <IconClock className="h-4 w-4" /> New follow-up
      </h3>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Call back about the proposal…" className="vbase-input md:col-span-2" />
        <label className="flex flex-col gap-1 text-xs text-[var(--vbase-slate500)]">
          Due
          <input type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} className="vbase-input" />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-xs text-[var(--vbase-slate500)]">
            Contact ID
            <input value={contactId} onChange={(e) => setContactId(e.target.value)} inputMode="numeric" placeholder="optional" className="vbase-input" />
          </label>
          <label className="flex flex-col gap-1 text-xs text-[var(--vbase-slate500)]">
            Company ID
            <input value={companyId} onChange={(e) => setCompanyId(e.target.value)} inputMode="numeric" placeholder="optional" className="vbase-input" />
          </label>
        </div>
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes (optional)" rows={2} className="vbase-input md:col-span-2" />
      </div>
      <div className="mt-4 flex items-center justify-end gap-2">
        <button onClick={onClose} className="vbase-btn-ghost flex items-center gap-1.5">
          <IconX className="h-4 w-4" /> Cancel
        </button>
        <button onClick={save} disabled={saving} className="vbase-btn-primary flex items-center gap-1.5">
          <IconCheck className="h-4 w-4" /> Save task
        </button>
      </div>
    </div>
  );
}
