import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  IconUpload,
  IconFileSpreadsheet,
  IconCheck,
  IconLoader2,
  IconChevronRight,
  IconDownload,
  IconHistory,
  IconPlus,
  IconAlertCircle,
  IconAlertTriangle,
  IconInfo,
  IconTable2Icon,
  IconSlidersHorizontalIcon,
  IconWandSparkles,
  IconArrowRight,
  IconArrowLeftRight,
  IconX,
  IconRefreshCcw,
  IconShieldCheck,
  IconLayers,
} from "@/lib/icons";
import { api, downloadFile, ApiError } from "@/lib/api";
import { toast } from "@/lib/store";
import { downloadCsv } from "@/lib/download";

// ---------------------------------------------------------------------------
// Contract mirrored from backend/src/nexus/api/v1/import_.py
// ---------------------------------------------------------------------------

interface Option { value: string; description: string }
interface ImportOptions {
  strategies: Option[];
  update_modes: Option[];
  target_fields: { company: string[]; contact: string[] };
  max_upload_bytes: number;
  allowed_extensions: string[];
}

interface UploadResult {
  job_id: number;
  filename: string;
  file_size_bytes: number;
  status: string;
  sheet_names: string[];
  default_sheet: string | null;
  is_spreadsheet: boolean;
}

interface PreviewResult {
  job_id: number;
  filename: string;
  sheet_name: string | null;
  sheet_names: string[];
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  col_count: number;
  total_rows_estimate: number;
  suggested_mapping: Record<string, string>;
}

interface FieldChange { field: string; from: unknown; to: unknown; action: "fill" | "overwrite" }
interface PlanItem {
  row_index: number;
  action: PlanAction;
  entity?: string | null;
  reason?: string | null;
  changes?: Record<string, FieldChange>;
  duplicate_of?: number | null;
}
type PlanAction = "added" | "updated" | "unchanged" | "skipped" | "invalid" | "duplicate";

interface PlanResult {
  job_id: number;
  strategy: string;
  update_mode: string;
  rows_total: number;
  previewed: number;
  counts: Record<PlanAction, number>;
  items: PlanItem[];
  truncated: boolean;
}

interface JobSummary {
  id: number;
  filename: string;
  file_size_bytes: number | null;
  status: string;
  strategy: string | null;
  update_mode: string | null;
  sheet_name: string | null;
  rows_total: number | null;
  rows_processed: number | null;
  rows_added: number | null;
  rows_updated: number | null;
  rows_unchanged: number | null;
  rows_duplicate: number | null;
  rows_invalid: number | null;
  rows_skipped: number | null;
  error_summary: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
  by_status?: Record<string, number>;
  sheet_names?: string[];
}

interface ProgressResult {
  job_id: number;
  status: string;
  rows_total: number;
  rows_processed: number;
  percent: number;
  by_status: Record<string, number>;
  error_summary: string | null;
}

type Step = "upload" | "preview" | "mapping" | "review" | "running" | "done" | "history";

const STEPS: { id: Step; label: string }[] = [
  { id: "upload", label: "Upload" },
  { id: "preview", label: "Preview" },
  { id: "mapping", label: "Mapping" },
  { id: "review", label: "Review" },
  { id: "running", label: "Import" },
  { id: "done", label: "Results" },
];

const ACTION_STYLE: Record<string, { label: string; className: string }> = {
  added: { label: "Add", className: "bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]" },
  updated: { label: "Update", className: "bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]" },
  unchanged: { label: "No change", className: "bg-[var(--vbase-bg-alt)] text-[var(--vbase-slate500)]" },
  skipped: { label: "Skip", className: "bg-[var(--vbase-amber)]/10 text-[var(--vbase-amber)]" },
  duplicate: { label: "Duplicate", className: "bg-[var(--vbase-amber)]/10 text-[var(--vbase-amber)]" },
  invalid: { label: "Invalid", className: "bg-[var(--vbase-red)]/10 text-[var(--vbase-red)]" },
};

function fmtBytes(n: number | null | undefined) {
  if (!n) return "—";
  if (n > 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + " MB";
  if (n > 1024) return Math.round(n / 1024) + " KB";
  return n + " B";
}

function fmtValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function humanize(field: string) {
  return field.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ---------------------------------------------------------------------------

export function ImportPage() {
  const [step, setStep] = useState<Step>("upload");
  const [options, setOptions] = useState<ImportOptions | null>(null);
  const [upload, setUpload] = useState<UploadResult | null>(null);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [strategy, setStrategy] = useState("add_and_update");
  const [updateMode, setUpdateMode] = useState("fill_empty");
  const [allowDuplicateCreates, setAllowDuplicateCreates] = useState(false);
  const [plan, setPlan] = useState<PlanResult | null>(null);
  const [result, setResult] = useState<JobSummary | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<ImportOptions>("/import/options")
      .then(setOptions)
      .catch(() => toast("Could not load import options", "error"));
  }, []);

  const reset = useCallback(() => {
    setUpload(null);
    setPreview(null);
    setMapping({});
    setStrategy("add_and_update");
    setUpdateMode("fill_empty");
    setAllowDuplicateCreates(false);
    setPlan(null);
    setResult(null);
    setBusy(null);
    setStep("upload");
  }, []);

  const loadPreview = useCallback(async (jobId: number, sheet?: string) => {
    const data = await api.get<PreviewResult>(`/import/preview/${jobId}`, {
      params: { sheet: sheet || undefined, limit: 50 },
    });
    setPreview(data);
    setMapping((prev) => (Object.keys(prev).length ? prev : data.suggested_mapping || {}));
    return data;
  }, []);

  const onUploaded = useCallback(
    async (res: UploadResult) => {
      setUpload(res);
      setMapping({});
      if (res.sheet_names.length > 1) {
        // Let the user choose the worksheet before pulling rows.
        setPreview(null);
        setStep("preview");
        return;
      }
      await loadPreview(res.job_id);
      setStep("preview");
    },
    [loadPreview]
  );

  const chooseSheet = async (sheet: string) => {
    if (!upload) return;
    setBusy("sheet");
    try {
      const data = await loadPreview(upload.job_id, sheet);
      setUpload({ ...upload, sheet_names: data.sheet_names, default_sheet: data.sheet_name });
      const suggested = data.suggested_mapping || {};
      setMapping(suggested);
      toast(`Worksheet “${sheet}” loaded`, "success");
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Could not read that worksheet", "error");
    } finally {
      setBusy(null);
    }
  };

  const saveMapping = async (nextStep: Step) => {
    if (!upload) return;
    const usable = Object.fromEntries(Object.entries(mapping).filter(([, v]) => v));
    if (!Object.keys(usable).length) {
      toast("Map at least one column before continuing", "error");
      return;
    }
    const duplicates = Object.entries(usable)
      .filter(([, v]) => v === "email")
      .length;
    if (duplicates > 1) {
      toast("Only one column can map to Email", "error");
      return;
    }
    setBusy("mapping");
    try {
      await api.post(`/import/mapping/${upload.job_id}`, {
        mapping: usable,
        strategy,
        update_mode: updateMode,
        sheet_name: preview?.sheet_name ?? undefined,
      });
      setMapping(usable);
      setStep(nextStep);
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Could not save the mapping", "error");
    } finally {
      setBusy(null);
    }
  };

  const runDryRun = async () => {
    if (!upload) return;
    setBusy("plan");
    try {
      const data = await api.get<PlanResult>(`/import/plan/${upload.job_id}`, { params: { limit: 100 } });
      setPlan(data);
      setStep("review");
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Dry run failed", "error");
    } finally {
      setBusy(null);
    }
  };

  const runImport = async () => {
    if (!upload) return;
    setStep("running");
    try {
      const summary = await api.post<JobSummary>(`/import/run/${upload.job_id}`, undefined, {
        params: { allow_duplicate_creates: allowDuplicateCreates },
      });
      setResult(summary);
      setStep("done");
      toast(
        `Import finished — ${summary.rows_added ?? 0} added, ${summary.rows_updated ?? 0} updated`,
        "success"
      );
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Import failed and was rolled back", "error");
      setStep("review");
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Import Center</h1>
          <p className="mt-0.5 text-sm text-[var(--vbase-slate500)]">
            CSV and XLSX imports with mapping, duplicate handling, a dry run and a full audit trail.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setStep(step === "history" ? "upload" : "history")}
            className="vbase-btn-secondary flex items-center gap-1.5"
          >
            <IconHistory className="h-4 w-4" />
            <span>{step === "history" ? "Back to import" : "History"}</span>
          </button>
          {step !== "upload" && step !== "history" && (
            <button onClick={reset} className="vbase-btn-ghost flex items-center gap-1.5">
              <IconRefreshCcw className="h-4 w-4" />
              <span>Start over</span>
            </button>
          )}
        </div>
      </div>

      {step !== "history" && (
        <ol className="flex flex-wrap items-center gap-1.5">
          {STEPS.map((s, i) => {
            const currentIndex = STEPS.findIndex((x) => x.id === step);
            const state = i < currentIndex ? "done" : i === currentIndex ? "active" : "todo";
            return (
              <li key={s.id} className="flex items-center gap-1.5">
                <span
                  className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-xs font-medium ${
                    state === "active"
                      ? "bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]"
                      : state === "done"
                      ? "text-[var(--vbase-green)]"
                      : "text-[var(--vbase-slate400)]"
                  }`}
                >
                  {state === "done" ? <IconCheck className="h-3.5 w-3.5" /> : <span>{i + 1}</span>}
                  {s.label}
                </span>
                {i < STEPS.length - 1 && <IconChevronRight className="h-3.5 w-3.5 text-[var(--vbase-slate300)]" />}
              </li>
            );
          })}
        </ol>
      )}

      {step === "upload" && <UploadStep options={options} onUploaded={onUploaded} onHistory={() => setStep("history")} />}

      {step === "preview" && upload && (
        <PreviewStep
          upload={upload}
          preview={preview}
          busy={busy}
          onChooseSheet={chooseSheet}
          onBack={reset}
          onContinue={() => {
            if (!preview) {
              toast("Choose a worksheet first", "error");
              return;
            }
            setStep("mapping");
          }}
        />
      )}

      {step === "mapping" && preview && options && (
        <MappingStep
          preview={preview}
          options={options}
          mapping={mapping}
          setMapping={setMapping}
          strategy={strategy}
          setStrategy={setStrategy}
          updateMode={updateMode}
          setUpdateMode={setUpdateMode}
          allowDuplicateCreates={allowDuplicateCreates}
          setAllowDuplicateCreates={setAllowDuplicateCreates}
          busy={busy}
          onBack={() => setStep("preview")}
          onReview={async () => {
            await saveMapping("review");
            await runDryRun();
          }}
        />
      )}

      {step === "review" && plan && (
        <ReviewStep
          plan={plan}
          strategy={strategy}
          updateMode={updateMode}
          allowDuplicateCreates={allowDuplicateCreates}
          busy={busy}
          onBack={() => setStep("mapping")}
          onRefresh={runDryRun}
          onRun={runImport}
        />
      )}

      {step === "running" && upload && <RunningStep jobId={upload.job_id} />}

      {step === "done" && result && <ResultStep job={result} onReset={reset} onHistory={() => setStep("history")} />}

      {step === "history" && <HistoryStep onResume={(job) => { setResult(job); setStep("done"); }} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 1 — upload
// ---------------------------------------------------------------------------

function UploadStep({
  options,
  onUploaded,
  onHistory,
}: {
  options: ImportOptions | null;
  onUploaded: (res: UploadResult) => void;
  onHistory: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  const maxMb = options ? Math.round(options.max_upload_bytes / (1024 * 1024)) : 50;
  const allowed = options?.allowed_extensions ?? [".csv", ".xlsx", ".xls"];

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    setError("");
    const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
    if (!allowed.includes(ext)) {
      setError(`Unsupported file type ${ext}. Allowed: ${allowed.join(", ")}`);
      return;
    }
    if (file.size > (options?.max_upload_bytes ?? 50 * 1024 * 1024)) {
      setError(`File is larger than ${maxMb}MB`);
      return;
    }
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await api.post<UploadResult>("/import/upload", form);
      toast(`${res.filename} uploaded`, "success");
      onUploaded(res);
    } catch (e: any) {
      setError(e?.data?.detail || e?.message || "Upload failed");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFile(e.dataTransfer.files?.[0]);
        }}
        className={`vbase-card flex flex-col items-center gap-4 p-12 text-center transition-colors ${
          dragging ? "border-[var(--vbase-indigo)] bg-[var(--vbase-indigo)]/5" : ""
        }`}
      >
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]">
          {uploading ? <IconLoader2 className="h-8 w-8 animate-spin" /> : <IconUpload className="h-8 w-8" />}
        </div>
        <div>
          <h2 className="text-lg font-semibold text-[var(--vbase-slate800)]">
            {uploading ? "Uploading and validating…" : "Drop a spreadsheet here"}
          </h2>
          <p className="mt-1 text-sm text-[var(--vbase-slate500)]">
            CSV, XLSX and XLS up to {maxMb}MB. The file signature is checked before it is stored.
          </p>
        </div>
        <button
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          className="vbase-btn-primary flex items-center gap-2"
        >
          <IconFileSpreadsheet className="h-4 w-4" />
          <span>Choose file</span>
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={allowed.join(",")}
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
        <p className="text-xs uppercase tracking-wider text-[var(--vbase-slate400)]">
          {allowed.join(" · ")}
        </p>
        {error && (
          <p className="flex items-center gap-1.5 text-sm text-[var(--vbase-red)]">
            <IconAlertCircle className="h-4 w-4" />
            {error}
          </p>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <InfoTile
          icon={<IconShieldCheck className="h-4 w-4" />}
          title="Nothing is written yet"
          body="Uploads only store the file. Rows are classified and previewed before any record is created."
        />
        <InfoTile
          icon={<IconWandSparkles className="h-4 w-4" />}
          title="Automatic mapping"
          body="Column headers are matched to V-Base fields automatically — every one stays editable."
        />
        <InfoTile
          icon={<IconLayers className="h-4 w-4" />}
          title="One transaction"
          body="A failed import rolls back completely. Existing values are never overwritten silently."
        />
      </div>

      <button onClick={onHistory} className="self-start text-sm font-medium text-[var(--vbase-indigo)] hover:underline">
        View previous imports →
      </button>
    </div>
  );
}

function InfoTile({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <div className="vbase-card p-4">
      <p className="flex items-center gap-2 text-sm font-semibold text-[var(--vbase-slate800)]">
        <span className="text-[var(--vbase-indigo)]">{icon}</span>
        {title}
      </p>
      <p className="mt-1.5 text-xs leading-relaxed text-[var(--vbase-slate500)]">{body}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 2 — preview & worksheet selection
// ---------------------------------------------------------------------------

function PreviewStep({
  upload,
  preview,
  busy,
  onChooseSheet,
  onBack,
  onContinue,
}: {
  upload: UploadResult;
  preview: PreviewResult | null;
  busy: string | null;
  onChooseSheet: (sheet: string) => void;
  onBack: () => void;
  onContinue: () => void;
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="vbase-card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--vbase-border)] px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-[var(--vbase-bg-alt)]">
              <IconFileSpreadsheet className="h-4 w-4 text-[var(--vbase-slate500)]" />
            </div>
            <div>
              <p className="font-medium text-[var(--vbase-slate800)]">{upload.filename}</p>
              <p className="text-xs text-[var(--vbase-slate500)]">
                {fmtBytes(upload.file_size_bytes)}
                {preview ? ` · ${preview.total_rows_estimate || preview.row_count} rows · ${preview.columns.length} columns` : ""}
              </p>
            </div>
          </div>

          {upload.sheet_names.length > 1 && (
            <label className="flex items-center gap-2 text-sm">
              <span className="text-[var(--vbase-slate500)]">Worksheet</span>
              <select
                value={preview?.sheet_name ?? upload.default_sheet ?? ""}
                onChange={(e) => onChooseSheet(e.target.value)}
                disabled={busy === "sheet"}
                className="vbase-select w-48"
              >
                {upload.sheet_names.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              {busy === "sheet" && <IconLoader2 className="h-4 w-4 animate-spin text-[var(--vbase-slate400)]" />}
            </label>
          )}
        </div>

        {!preview ? (
          <div className="flex flex-col items-center gap-2 py-16 text-sm text-[var(--vbase-slate500)]">
            <IconLayers className="h-8 w-8 text-[var(--vbase-slate300)]" />
            Choose a worksheet to preview its rows.
          </div>
        ) : (
          <>
            <div className="max-h-[380px] overflow-auto">
              <table className="vbase-table">
                <thead>
                  <tr>
                    <th className="w-12 text-left">#</th>
                    {preview.columns.map((col) => (
                      <th key={col} className="whitespace-nowrap text-left">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.slice(0, 25).map((row, i) => (
                    <tr key={i}>
                      <td className="text-xs text-[var(--vbase-slate400)]">{i + 1}</td>
                      {preview.columns.map((col) => {
                        const raw = row[col];
                        return (
                          <td key={col} className="max-w-[260px] truncate text-sm text-[var(--vbase-slate700)]">
                            {raw === null || raw === undefined || raw === "" ? (
                              <span className="text-[var(--vbase-slate400)]">—</span>
                            ) : (
                              String(raw)
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="border-t border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] px-4 py-2 text-xs text-[var(--vbase-slate500)]">
              Showing {Math.min(25, preview.row_count)} of {preview.total_rows_estimate || preview.row_count} rows
              {preview.total_rows_estimate > preview.row_count ? " (preview is capped)" : ""}
            </div>
          </>
        )}
      </div>

      <div className="flex items-center justify-between">
        <button onClick={onBack} className="vbase-btn-ghost flex items-center gap-1.5">
          <IconX className="h-4 w-4" />
          <span>Discard file</span>
        </button>
        <button onClick={onContinue} disabled={!preview} className="vbase-btn-primary flex items-center gap-1.5">
          <span>Continue to mapping</span>
          <IconChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 3 — mapping, strategy, duplicate handling
// ---------------------------------------------------------------------------

function MappingStep({
  preview,
  options,
  mapping,
  setMapping,
  strategy,
  setStrategy,
  updateMode,
  setUpdateMode,
  allowDuplicateCreates,
  setAllowDuplicateCreates,
  busy,
  onBack,
  onReview,
}: {
  preview: PreviewResult;
  options: ImportOptions;
  mapping: Record<string, string>;
  setMapping: (m: Record<string, string>) => void;
  strategy: string;
  setStrategy: (s: string) => void;
  updateMode: string;
  setUpdateMode: (m: string) => void;
  allowDuplicateCreates: boolean;
  setAllowDuplicateCreates: (v: boolean) => void;
  busy: string | null;
  onBack: () => void;
  onReview: () => void;
}) {
  const companyFields = options.target_fields.company;
  const contactFields = options.target_fields.contact;

  const sample = (col: string) => {
    for (const row of preview.rows) {
      const v = row[col];
      if (v !== null && v !== undefined && v !== "") return String(v);
    }
    return "";
  };

  const duplicates = useMemo(() => {
    const counts: Record<string, number> = {};
    Object.values(mapping).forEach((v) => {
      if (v) counts[v] = (counts[v] || 0) + 1;
    });
    return Object.entries(counts).filter(([, n]) => n > 1).map(([field]) => field);
  }, [mapping]);

  return (
    <div className="flex flex-col gap-4">
      <div className="vbase-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="font-semibold text-[var(--vbase-slate800)]">Column mapping</h3>
            <p className="mt-0.5 text-sm text-[var(--vbase-slate500)]">
              Suggested automatically from the headers. Unmapped columns are ignored.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setMapping(preview.suggested_mapping || {})}
              className="vbase-btn-secondary flex items-center gap-1.5"
            >
              <IconWandSparkles className="h-4 w-4" />
              <span>Reset to suggestions</span>
            </button>
            <button
              onClick={() => setMapping(Object.fromEntries(Object.keys(mapping).map((k) => [k, ""])))}
              className="vbase-btn-ghost"
            >
              Clear all
            </button>
          </div>
        </div>

        {duplicates.length > 0 && (
          <p className="mt-3 flex items-center gap-2 rounded-md border border-[var(--vbase-red)]/25 bg-[var(--vbase-red)]/5 px-3 py-2 text-sm text-[var(--vbase-red)]">
            <IconAlertTriangle className="h-4 w-4" />
            {duplicates.map(humanize).join(", ")} is mapped from more than one column.
          </p>
        )}

        <div className="mt-4 max-h-[420px] space-y-2 overflow-auto pr-1">
          {preview.columns.map((col) => (
            <div
              key={col}
              className={`flex items-center gap-3 rounded-md border px-3 py-2 ${
                mapping[col]
                  ? "border-[var(--vbase-border)] bg-[var(--vbase-bg)]"
                  : "border-dashed border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)]"
              }`}
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-[var(--vbase-slate800)]">{col}</p>
                <p className="truncate text-xs text-[var(--vbase-slate500)]">
                  {sample(col) ? `e.g. ${sample(col)}` : "no sample value"}
                </p>
              </div>
              <IconArrowRight className="h-4 w-4 flex-shrink-0 text-[var(--vbase-slate300)]" />
              <select
                value={mapping[col] || ""}
                onChange={(e) => setMapping({ ...mapping, [col]: e.target.value })}
                className={`vbase-select w-60 ${mapping[col] ? "" : "text-[var(--vbase-slate400)]"}`}
              >
                <option value="">— ignore this column —</option>
                <optgroup label="Company">
                  {companyFields.map((f) => (
                    <option key={f} value={f}>
                      {humanize(f)}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Contact / person">
                  {contactFields.map((f) => (
                    <option key={f} value={f}>
                      {humanize(f)}
                    </option>
                  ))}
                </optgroup>
              </select>
            </div>
          ))}
        </div>

        <p className="mt-4 border-t border-[var(--vbase-border)] pt-3 text-sm text-[var(--vbase-slate500)]">
          <strong className="font-medium text-[var(--vbase-slate700)]">
            {Object.values(mapping).filter(Boolean).length}
          </strong>{" "}
          of {preview.columns.length} columns mapped.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="vbase-card p-5">
          <h3 className="mb-1 flex items-center gap-2 font-semibold text-[var(--vbase-slate800)]">
            <IconSlidersHorizontalIcon className="h-4 w-4" />
            What should happen to matching rows?
          </h3>
          <p className="mb-4 text-sm text-[var(--vbase-slate500)]">
            Records are matched on email, then name and company, for contacts — and on domain, then website, then name
            for companies.
          </p>
          <div className="space-y-2">
            {options.strategies.map((s) => (
              <label
                key={s.value}
                className={`flex cursor-pointer items-start gap-3 rounded-md border p-3 transition-colors ${
                  strategy === s.value
                    ? "border-[var(--vbase-indigo)] bg-[var(--vbase-indigo)]/5"
                    : "border-[var(--vbase-border)] hover:bg-[var(--vbase-bg-alt)]"
                }`}
              >
                <input
                  type="radio"
                  name="strategy"
                  checked={strategy === s.value}
                  onChange={() => setStrategy(s.value)}
                  className="mt-1"
                />
                <span>
                  <span className="block text-sm font-medium text-[var(--vbase-slate800)]">
                    {humanize(s.value)}
                  </span>
                  <span className="block text-xs text-[var(--vbase-slate500)]">{s.description}</span>
                </span>
              </label>
            ))}
          </div>
        </div>

        <div className="vbase-card p-5">
          <h3 className="mb-1 flex items-center gap-2 font-semibold text-[var(--vbase-slate800)]">
            <IconArrowLeftRight className="h-4 w-4" />
            When updating an existing record
          </h3>
          <p className="mb-4 text-sm text-[var(--vbase-slate500)]">
            This is the guarantee that an import never destroys data you already curated.
          </p>
          <div className="space-y-2">
            {options.update_modes.map((m) => (
              <label
                key={m.value}
                className={`flex cursor-pointer items-start gap-3 rounded-md border p-3 transition-colors ${
                  updateMode === m.value
                    ? "border-[var(--vbase-indigo)] bg-[var(--vbase-indigo)]/5"
                    : "border-[var(--vbase-border)] hover:bg-[var(--vbase-bg-alt)]"
                }`}
              >
                <input
                  type="radio"
                  name="update_mode"
                  checked={updateMode === m.value}
                  onChange={() => setUpdateMode(m.value)}
                  className="mt-1"
                />
                <span>
                  <span className="block text-sm font-medium text-[var(--vbase-slate800)]">
                    {m.value === "fill_empty" ? "Fill blanks only (safe)" : "Overwrite existing values"}
                  </span>
                  <span className="block text-xs text-[var(--vbase-slate500)]">{m.description}</span>
                </span>
              </label>
            ))}
          </div>

          {updateMode === "overwrite" && (
            <p className="mt-3 flex items-start gap-2 rounded-md border border-[var(--vbase-amber)]/30 bg-[var(--vbase-amber)]/5 px-3 py-2 text-xs text-[var(--vbase-slate700)]">
              <IconAlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-[var(--vbase-amber)]" />
              Every replaced value is shown in the next step and recorded in the import report and activity log.
            </p>
          )}

          <label className="mt-4 flex items-start gap-3 border-t border-[var(--vbase-border)] pt-4">
            <input
              type="checkbox"
              checked={allowDuplicateCreates}
              onChange={(e) => setAllowDuplicateCreates(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              <span className="block text-sm font-medium text-[var(--vbase-slate800)]">
                Import likely duplicates anyway
              </span>
              <span className="block text-xs text-[var(--vbase-slate500)]">
                Off by default. When on, rows that look like a duplicate are still inserted and flagged for the
                Duplicates page instead of being skipped.
              </span>
            </span>
          </label>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <button onClick={onBack} className="vbase-btn-ghost flex items-center gap-1.5">
          <IconX className="h-4 w-4" />
          <span>Back to preview</span>
        </button>
        <button onClick={onReview} disabled={busy === "mapping" || busy === "plan"} className="vbase-btn-primary flex items-center gap-1.5">
          {busy === "mapping" || busy === "plan" ? (
            <IconLoader2 className="h-4 w-4 animate-spin" />
          ) : (
            <IconWandSparkles className="h-4 w-4" />
          )}
          <span>Preview changes (dry run)</span>
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 4 — dry run review
// ---------------------------------------------------------------------------

function ReviewStep({
  plan,
  strategy,
  updateMode,
  allowDuplicateCreates,
  busy,
  onBack,
  onRefresh,
  onRun,
}: {
  plan: PlanResult;
  strategy: string;
  updateMode: string;
  allowDuplicateCreates: boolean;
  busy: string | null;
  onBack: () => void;
  onRefresh: () => void;
  onRun: () => void;
}) {
  const [filter, setFilter] = useState<PlanAction | "all">("all");

  const items = plan.items.filter((i) => filter === "all" || i.action === filter);
  const willWrite = (plan.counts.added || 0) + (plan.counts.updated || 0);
  const overwrites = plan.items.reduce(
    (sum, item) =>
      sum + Object.values(item.changes || {}).filter((c) => c.action === "overwrite").length,
    0
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <PlanStat label="Rows" value={plan.rows_total} />
        <PlanStat label="Add" value={plan.counts.added || 0} tone="green" />
        <PlanStat label="Update" value={plan.counts.updated || 0} tone="indigo" />
        <PlanStat label="No change" value={plan.counts.unchanged || 0} />
        <PlanStat label="Skip" value={plan.counts.skipped || 0} tone="amber" />
        <PlanStat label="Invalid" value={plan.counts.invalid || 0} tone="red" />
      </div>

      <div className="vbase-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="flex items-start gap-2 text-sm text-[var(--vbase-slate600)]">
            <IconInfo className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--vbase-slate400)]" />
            <span>
              Dry run against the live database — <strong>nothing has been written</strong>. Strategy{" "}
              <code className="rounded bg-[var(--vbase-bg-alt)] px-1 font-mono text-xs">{strategy}</code>, update mode{" "}
              <code className="rounded bg-[var(--vbase-bg-alt)] px-1 font-mono text-xs">{updateMode}</code>
              {overwrites > 0 && (
                <>
                  . <strong className="text-[var(--vbase-amber)]">{overwrites}</strong> existing value
                  {overwrites === 1 ? "" : "s"} would be overwritten.
                </>
              )}
              {allowDuplicateCreates && " Duplicate insertion is enabled for this run."}
            </span>
          </p>
          <div className="flex items-center gap-2">
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value as PlanAction | "all")}
              className="vbase-select w-40"
            >
              <option value="all">All actions</option>
              <option value="added">Add</option>
              <option value="updated">Update</option>
              <option value="unchanged">No change</option>
              <option value="skipped">Skip</option>
              <option value="invalid">Invalid</option>
            </select>
            <button onClick={onRefresh} className="vbase-btn-secondary flex items-center gap-1.5">
              <IconRefreshCcw className="h-4 w-4" />
              <span>Re-run</span>
            </button>
          </div>
        </div>
      </div>

      <div className="vbase-card overflow-hidden">
        <div className="border-b border-[var(--vbase-border)] px-4 py-3">
          <h3 className="font-semibold text-[var(--vbase-slate800)]">
            Row-by-row plan ({items.length}
            {plan.truncated ? ` of first ${plan.previewed}` : ""})
          </h3>
        </div>
        <div className="divide-y divide-[var(--vbase-border)]">
          {items.map((item) => {
            const changes = Object.values(item.changes || {});
            const style = ACTION_STYLE[item.action] || ACTION_STYLE.unchanged;
            return (
              <div key={item.row_index} className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-[var(--vbase-slate400)]">row {item.row_index + 1}</span>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${style.className}`}>
                    {style.label}
                  </span>
                  {item.entity && (
                    <span className="rounded-full bg-[var(--vbase-bg-alt)] px-2 py-0.5 text-xs text-[var(--vbase-slate600)]">
                      {item.entity}
                    </span>
                  )}
                  {item.duplicate_of && (
                    <span className="text-xs text-[var(--vbase-slate500)]">
                      matches existing #{item.duplicate_of}
                    </span>
                  )}
                  {item.reason && <span className="text-xs text-[var(--vbase-slate500)]">{item.reason}</span>}
                </div>

                {changes.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {changes.map((c) => (
                      <div
                        key={c.field}
                        className="flex flex-wrap items-center gap-2 rounded-md bg-[var(--vbase-bg-alt)] px-2.5 py-1.5 text-xs"
                      >
                        <span className="font-medium text-[var(--vbase-slate700)]">{humanize(c.field)}</span>
                        <span className="text-[var(--vbase-slate400)] line-through">{fmtValue(c.from)}</span>
                        <IconChevronRight className="h-3 w-3 text-[var(--vbase-slate400)]" />
                        <span className="font-medium text-[var(--vbase-slate900)]">{fmtValue(c.to)}</span>
                        <span
                          className={`ml-auto rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                            c.action === "overwrite"
                              ? "bg-[var(--vbase-amber)]/15 text-[var(--vbase-amber)]"
                              : "bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]"
                          }`}
                        >
                          {c.action === "overwrite" ? "overwrite" : "fill blank"}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
          {!items.length && (
            <p className="px-4 py-10 text-center text-sm text-[var(--vbase-slate500)]">
              No rows match this filter.
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <button onClick={onBack} className="vbase-btn-ghost flex items-center gap-1.5">
          <IconX className="h-4 w-4" />
          <span>Adjust mapping</span>
        </button>
        <div className="flex items-center gap-3">
          <span className="text-sm text-[var(--vbase-slate500)]">
            {willWrite} record{willWrite === 1 ? "" : "s"} will be written
          </span>
          <button
            onClick={onRun}
            disabled={busy === "run" || willWrite === 0}
            className="vbase-btn-primary flex items-center gap-1.5"
          >
            {busy === "run" ? <IconLoader2 className="h-4 w-4 animate-spin" /> : <IconCheck className="h-4 w-4" />}
            <span>Run import</span>
          </button>
        </div>
      </div>
    </div>
  );
}

function PlanStat({ label, value, tone }: { label: string; value: number; tone?: "green" | "indigo" | "amber" | "red" }) {
  const color =
    tone === "green"
      ? "text-[var(--vbase-green)]"
      : tone === "indigo"
      ? "text-[var(--vbase-indigo)]"
      : tone === "amber"
      ? "text-[var(--vbase-amber)]"
      : tone === "red"
      ? "text-[var(--vbase-red)]"
      : "text-[var(--vbase-slate900)]";
  return (
    <div className="vbase-card px-4 py-3">
      <p className="text-xs uppercase tracking-wider text-[var(--vbase-slate500)]">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${color}`}>{value}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 5 — running with live progress
// ---------------------------------------------------------------------------

function RunningStep({ jobId }: { jobId: number }) {
  const [progress, setProgress] = useState<ProgressResult | null>(null);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const startedAt = Date.now();
    const timer = window.setInterval(() => setElapsed(Math.round((Date.now() - startedAt) / 1000)), 1000);
    let cancelled = false;

    const poll = async () => {
      while (!cancelled) {
        try {
          const data = await api.get<ProgressResult>(`/import/progress/${jobId}`);
          if (cancelled) return;
          setProgress(data);
          if (data.status && !["running", "pending"].includes(data.status)) return;
        } catch {
          /* transient — keep polling while the transaction commits */
        }
        await new Promise((r) => window.setTimeout(r, 700));
      }
    };
    poll();

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [jobId]);

  const percent = progress?.percent ?? 0;

  return (
    <div className="vbase-card flex flex-col items-center gap-4 p-12 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]">
        <IconLoader2 className="h-7 w-7 animate-spin" />
      </div>
      <div>
        <h2 className="text-lg font-semibold text-[var(--vbase-slate800)]">Importing in one transaction</h2>
        <p className="mt-1 text-sm text-[var(--vbase-slate500)]">
          Every row is being applied. The whole run commits once — a failure rolls everything back.
        </p>
      </div>

      <div className="w-full max-w-lg">
        <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--vbase-bg-alt)]">
          <div
            className="h-full rounded-full bg-[var(--vbase-indigo)] transition-all duration-300"
            style={{ width: `${Math.max(percent, 4)}%` }}
          />
        </div>
        <div className="mt-2 flex items-center justify-between text-xs text-[var(--vbase-slate500)]">
          <span>
            {progress ? `${progress.rows_processed} of ${progress.rows_total} rows` : "waiting for the first row…"}
          </span>
          <span>{elapsed}s elapsed</span>
        </div>
      </div>

      {progress && Object.keys(progress.by_status || {}).length > 0 && (
        <div className="flex flex-wrap justify-center gap-2">
          {Object.entries(progress.by_status).map(([status, count]) => (
            <span key={status} className="rounded-full bg-[var(--vbase-bg-alt)] px-2.5 py-1 text-xs text-[var(--vbase-slate600)]">
              {status}: {count}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 6 — results
// ---------------------------------------------------------------------------

function ResultStep({
  job,
  onReset,
  onHistory,
}: {
  job: JobSummary;
  onReset: () => void;
  onHistory: () => void;
}) {
  const [detail, setDetail] = useState<JobSummary | null>(job);
  const [errors, setErrors] = useState<{ count: number; data: any[] } | null>(null);
  const [loadingErrors, setLoadingErrors] = useState(false);
  const [showErrors, setShowErrors] = useState(false);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    api
      .get<JobSummary>(`/import/${job.id}`)
      .then((d) => setDetail({ ...job, ...d }))
      .catch(() => {});
  }, [job]);

  const loadErrors = async () => {
    setLoadingErrors(true);
    try {
      const data = await api.get<{ count: number; data: any[] }>(`/import/errors/${job.id}`);
      setErrors(data);
      setShowErrors(true);
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Could not load the error report", "error");
    } finally {
      setLoadingErrors(false);
    }
  };

  const downloadReport = async (extension: "csv" | "xlsx") => {
    setDownloading(true);
    try {
      await downloadFile(`/import/download/${job.id}?extension=${extension}`, `vbase-import-${job.id}.${extension}`);
      toast(`Report downloaded as .${extension}`, "success");
    } catch (e: any) {
      const message = e instanceof ApiError ? e.message : e?.message || "Download failed";
      toast(message, "error");
    } finally {
      setDownloading(false);
    }
  };

  const failed = job.status !== "completed";
  const counters = [
    { label: "Rows processed", value: detail?.rows_processed ?? job.rows_processed ?? 0 },
    { label: "Added", value: detail?.rows_added ?? 0, tone: "green" as const },
    { label: "Updated", value: detail?.rows_updated ?? 0, tone: "indigo" as const },
    { label: "Unchanged", value: detail?.rows_unchanged ?? 0 },
    { label: "Duplicates", value: detail?.rows_duplicate ?? 0, tone: "amber" as const },
    { label: "Skipped", value: detail?.rows_skipped ?? 0, tone: "amber" as const },
    { label: "Invalid", value: detail?.rows_invalid ?? 0, tone: "red" as const },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="vbase-card p-6">
        <div className="flex items-start gap-3">
          <div
            className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full ${
              failed ? "bg-[var(--vbase-red)]/10 text-[var(--vbase-red)]" : "bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]"
            }`}
          >
            {failed ? <IconAlertCircle className="h-5 w-5" /> : <IconCheck className="h-5 w-5" />}
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="font-semibold text-[var(--vbase-slate800)]">
              {failed ? "Import did not complete" : "Import complete"}
            </h2>
            <p className="mt-0.5 text-sm text-[var(--vbase-slate500)]">
              {job.filename} · status <code className="font-mono text-xs">{job.status}</code>
              {job.strategy ? (
                <>
                  {" "}
                  · strategy <code className="font-mono text-xs">{job.strategy}</code>
                </>
              ) : null}
              {job.update_mode ? (
                <>
                  {" "}
                  · updates <code className="font-mono text-xs">{job.update_mode}</code>
                </>
              ) : null}
            </p>
            {job.error_summary && (
              <p className="mt-2 rounded-md border border-[var(--vbase-amber)]/30 bg-[var(--vbase-amber)]/5 px-3 py-2 text-xs text-[var(--vbase-slate700)]">
                {job.error_summary}
              </p>
            )}
          </div>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {counters.map((c) => (
            <PlanStat key={c.label} label={c.label} value={c.value} tone={c.tone} />
          ))}
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-[var(--vbase-border)] pt-4">
          <button onClick={() => downloadReport("csv")} disabled={downloading} className="vbase-btn-secondary flex items-center gap-1.5">
            {downloading ? <IconLoader2 className="h-4 w-4 animate-spin" /> : <IconDownload className="h-4 w-4" />}
            <span>Row report (CSV)</span>
          </button>
          <button onClick={() => downloadReport("xlsx")} disabled={downloading} className="vbase-btn-secondary flex items-center gap-1.5">
            <IconTable2Icon className="h-4 w-4" />
            <span>Row report (XLSX)</span>
          </button>
          {(detail?.rows_invalid || detail?.rows_skipped || detail?.rows_duplicate) ? (
            <button onClick={loadErrors} disabled={loadingErrors} className="vbase-btn-secondary flex items-center gap-1.5">
              {loadingErrors ? <IconLoader2 className="h-4 w-4 animate-spin" /> : <IconAlertTriangle className="h-4 w-4" />}
              <span>Error report</span>
            </button>
          ) : null}
          <div className="ml-auto flex items-center gap-2">
            <button onClick={onHistory} className="vbase-btn-ghost flex items-center gap-1.5">
              <IconHistory className="h-4 w-4" />
              <span>History</span>
            </button>
            <button onClick={onReset} className="vbase-btn-primary flex items-center gap-1.5">
              <IconPlus className="h-4 w-4" />
              <span>Import another file</span>
            </button>
          </div>
        </div>
      </div>

      {showErrors && errors && (
        <div className="vbase-card overflow-hidden">
          <div className="flex items-center justify-between border-b border-[var(--vbase-border)] px-4 py-3">
            <h3 className="font-semibold text-[var(--vbase-slate800)]">Skipped and invalid rows ({errors.count})</h3>
            <div className="flex items-center gap-2">
              <button
                onClick={() => downloadCsv(errors.data, `vbase-import-${job.id}-errors.csv`)}
                className="vbase-btn-secondary flex items-center gap-1.5"
              >
                <IconDownload className="h-4 w-4" />
                <span>Download CSV</span>
              </button>
              <button onClick={() => setShowErrors(false)} className="vbase-btn-ghost">
                Hide
              </button>
            </div>
          </div>
          <div className="max-h-[360px] overflow-auto">
            <table className="vbase-table">
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Severity</th>
                  <th>Field</th>
                  <th>Raw value</th>
                  <th>Message</th>
                </tr>
              </thead>
              <tbody>
                {errors.data.slice(0, 200).map((e, i) => (
                  <tr key={i}>
                    <td className="font-mono text-xs text-[var(--vbase-slate500)]">{(e.row_index ?? 0) + 1}</td>
                    <td>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          e.severity === "error"
                            ? "bg-[var(--vbase-red)]/10 text-[var(--vbase-red)]"
                            : "bg-[var(--vbase-amber)]/10 text-[var(--vbase-amber)]"
                        }`}
                      >
                        {e.severity}
                      </span>
                    </td>
                    <td className="text-[var(--vbase-slate600)]">{e.field || "—"}</td>
                    <td className="max-w-[220px] truncate text-[var(--vbase-slate500)]">{e.raw_value || "—"}</td>
                    <td className="text-[var(--vbase-slate700)]">{e.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// History
// ---------------------------------------------------------------------------

function HistoryStep({ onResume }: { onResume: (job: JobSummary) => void }) {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.get<{ jobs: JobSummary[]; total: number }>("/import/history", {
        params: { page, page_size: 20 },
      });
      setJobs(data.jobs || []);
      setTotal(data.total || 0);
    } catch (e: any) {
      setError(e?.data?.detail || e?.message || "Could not load import history");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    load();
  }, [load]);

  const pages = Math.max(1, Math.ceil(total / 20));

  return (
    <div className="vbase-card overflow-hidden">
      <div className="flex items-center justify-between border-b border-[var(--vbase-border)] px-4 py-3">
        <h3 className="font-semibold text-[var(--vbase-slate800)]">Import history ({total})</h3>
        <button onClick={load} className="vbase-btn-ghost flex items-center gap-1.5">
          <IconRefreshCcw className="h-4 w-4" />
          <span>Refresh</span>
        </button>
      </div>

      {loading ? (
        <div className="flex flex-col items-center gap-2 py-16 text-sm text-[var(--vbase-slate500)]">
          <IconLoader2 className="h-6 w-6 animate-spin text-[var(--vbase-indigo)]" />
          Loading imports…
        </div>
      ) : error ? (
        <div className="flex flex-col items-center gap-2 py-16 text-sm text-[var(--vbase-red)]">
          <IconAlertCircle className="h-6 w-6" />
          {error}
        </div>
      ) : jobs.length ? (
        <div className="overflow-x-auto">
          <table className="vbase-table">
            <thead>
              <tr>
                <th>File</th>
                <th>Started</th>
                <th>Status</th>
                <th>Strategy</th>
                <th className="text-right">Rows</th>
                <th className="text-right">Added</th>
                <th className="text-right">Updated</th>
                <th className="text-right">Skipped</th>
                <th className="text-right">Invalid</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id}>
                  <td>
                    <div className="flex items-center gap-2">
                      <IconFileSpreadsheet className="h-4 w-4 flex-shrink-0 text-[var(--vbase-slate500)]" />
                      <span className="max-w-[220px] truncate font-medium text-[var(--vbase-slate800)]">{j.filename}</span>
                    </div>
                  </td>
                  <td className="whitespace-nowrap text-[var(--vbase-slate500)]">
                    {j.created_at ? new Date(j.created_at).toLocaleString() : "—"}
                  </td>
                  <td>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        j.status === "completed"
                          ? "bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]"
                          : j.status === "running"
                          ? "bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]"
                          : "bg-[var(--vbase-bg-alt)] text-[var(--vbase-slate500)]"
                      }`}
                    >
                      {j.status}
                    </span>
                  </td>
                  <td className="text-xs text-[var(--vbase-slate500)]">{j.strategy || "—"}</td>
                  <td className="text-right">{j.rows_total ?? 0}</td>
                  <td className="text-right text-[var(--vbase-green)]">{j.rows_added ?? 0}</td>
                  <td className="text-right text-[var(--vbase-indigo)]">{j.rows_updated ?? 0}</td>
                  <td className="text-right">{j.rows_skipped ?? 0}</td>
                  <td className="text-right">{j.rows_invalid ?? 0}</td>
                  <td>
                    <button onClick={() => onResume(j)} className="vbase-btn-ghost text-xs">
                      Details
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-2 py-16 text-center text-sm text-[var(--vbase-slate500)]">
          <IconHistory className="h-8 w-8 text-[var(--vbase-slate300)]" />
          No imports yet.
        </div>
      )}

      {pages > 1 && (
        <div className="flex items-center justify-between border-t border-[var(--vbase-border)] px-4 py-3 text-sm">
          <span className="text-[var(--vbase-slate500)]">
            Page {page} of {pages}
          </span>
          <div className="flex items-center gap-2">
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} className="vbase-btn-secondary">
              Previous
            </button>
            <button onClick={() => setPage((p) => Math.min(pages, p + 1))} disabled={page === pages} className="vbase-btn-secondary">
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
