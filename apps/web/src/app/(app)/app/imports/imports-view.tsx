"use client";

import { ApiError } from "@sg/contracts";
import { ChevronsUpDown, Download, FileUp, ShieldAlert, Upload, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useId, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { EmptyState, ErrorState, PageHeader } from "@/components/states";
import { StatusPill } from "@/components/status";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  ACCEPTED,
  checkUpload,
  downloadRejected,
  type FieldOption,
  type ImportColumn,
  type ImportJob,
  type ImportSummary,
  phiBannerText,
  uploadImport,
  useCancelImport,
  useCommitImport,
  useImportFields,
  useImportHistory,
  useImportJob,
  useRemap,
  useSaveTemplate,
} from "@/hooks/use-imports";
import { cn } from "@/lib/utils";

const STATUS_LABEL: Record<ImportSummary["status"], string> = {
  uploaded: "Processing",
  parsed: "Processing",
  mapped: "Processing",
  validated: "Ready to review",
  committed: "Committed",
  failed: "Failed",
  cancelled: "Cancelled",
};
const STATUS_KIND = {
  uploaded: "info",
  parsed: "info",
  mapped: "info",
  validated: "warning",
  committed: "good",
  failed: "critical",
  cancelled: "info",
} as const;
const METHOD_LABEL: Record<NonNullable<ImportColumn["method"]>, string> = {
  exact: "Exact",
  synonym: "Synonym",
  fuzzy: "Fuzzy",
  template: "Template",
  ai: "AI",
  manual: "Manual",
};

const when = (iso: string) =>
  new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });

function errorText(err: unknown, fallback: string) {
  return err instanceof ApiError
    ? (err.detail ?? err.title)
    : err instanceof Error
      ? err.message
      : fallback;
}

/** Imports (SG-24): upload, review the mapping and validation, commit the valid rows. */
export function ImportsView({ departmentId, roles }: { departmentId: string; roles: string[] }) {
  const params = useSearchParams();
  const jobId = params.get("job");
  return jobId ? (
    <ImportReview
      departmentId={departmentId}
      jobId={jobId}
      isAdmin={roles.includes("dept_admin")}
    />
  ) : (
    <ImportsHome departmentId={departmentId} />
  );
}

function ImportsHome({ departmentId }: { departmentId: string }) {
  const history = useImportHistory(departmentId);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Data"
        title="Imports"
        description="Upload a daily log as CSV or Excel. Columns that look like names or IDs are removed before anything is stored. Nothing is saved until you commit."
      />
      <UploadZone departmentId={departmentId} />
      <section aria-labelledby="import-history" className="flex flex-col gap-3">
        <h2 id="import-history" className="engraved">
          History
        </h2>
        {history.isPending ? (
          <Skeleton className="h-32" aria-busy="true" />
        ) : history.isError ? (
          <ErrorState title="Imports could not be loaded" onRetry={() => history.refetch()} />
        ) : history.data.length === 0 ? (
          <EmptyState
            icon={FileUp}
            title="No imports yet"
            description="Uploaded files appear here."
          />
        ) : (
          <Table>
            <TableCaption className="sr-only">Import history, newest first</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>File</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Rows committed</TableHead>
                <TableHead>Who</TableHead>
                <TableHead>When</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {history.data.map((job) => (
                <TableRow key={job.id}>
                  <TableCell>
                    <Link
                      className="underline underline-offset-4"
                      href={`/app/imports?job=${job.id}`}
                    >
                      {job.original_filename}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <StatusPill status={STATUS_KIND[job.status]} label={STATUS_LABEL[job.status]} />
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {job.rows_committed ?? "—"}
                  </TableCell>
                  <TableCell>{job.created_by_me ? "You" : "Another steward"}</TableCell>
                  <TableCell className="whitespace-nowrap">{when(job.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>
    </div>
  );
}

export function UploadZone({ departmentId }: { departmentId: string }) {
  const router = useRouter();
  const inputId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function start(f: File) {
    setFile(f);
    const problem = checkUpload(f);
    if (problem) return setError(problem);
    setError(null);
    setProgress(0);
    try {
      const job = await uploadImport(departmentId, f, setProgress);
      router.push(`/app/imports?job=${job.id}`);
    } catch (err) {
      setError(errorText(err, "The upload failed."));
      setProgress(null);
    }
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        const f = e.dataTransfer.files[0];
        if (f) void start(f);
      }}
      className={cn(
        "flex flex-col items-center gap-3 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors",
        drag ? "border-primary bg-accent" : "border-border",
      )}
    >
      <Upload className="size-8 text-muted-foreground" aria-hidden />
      <p className="font-medium">Drop a file here, or choose one</p>
      <p className="text-13 text-muted-foreground">
        {ACCEPTED.join(", ")} up to 10 MB. Do not upload patient information.
      </p>
      <label htmlFor={inputId} className="sr-only">
        Choose a file to import
      </label>
      <input
        id={inputId}
        ref={input}
        type="file"
        accept={ACCEPTED.join(",")}
        className="sr-only"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void start(f);
          e.target.value = "";
        }}
      />
      <Button
        className="min-h-11"
        onClick={() => input.current?.click()}
        disabled={progress !== null}
      >
        <FileUp aria-hidden /> Choose file
      </Button>
      {file ? (
        <div className="flex w-full max-w-sm flex-col gap-1" aria-live="polite">
          <p className="truncate text-13 font-mono">{file.name}</p>
          {progress !== null ? (
            <>
              <progress className="h-2 w-full accent-primary" value={progress} max={1}>
                {Math.round(progress * 100)}%
              </progress>
              <p className="text-13 text-muted-foreground">
                {progress < 1 ? `Uploading ${Math.round(progress * 100)}%` : "Checking the file…"}
              </p>
            </>
          ) : null}
        </div>
      ) : null}
      {error ? (
        <p role="alert" className="text-sm text-status-critical">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function ImportReview({
  departmentId,
  jobId,
  isAdmin,
}: {
  departmentId: string;
  jobId: string;
  isAdmin: boolean;
}) {
  const job = useImportJob(departmentId, jobId);
  const fields = useImportFields(departmentId);
  if (job.isPending) return <Skeleton className="h-96" aria-busy="true" />;
  if (job.isError)
    return <ErrorState title="This import could not be loaded" onRetry={() => job.refetch()} />;
  return (
    <ReviewScreen
      departmentId={departmentId}
      job={job.data}
      fields={fields.data ?? []}
      isAdmin={isAdmin}
    />
  );
}

export function ReviewScreen({
  departmentId,
  job,
  fields,
  isAdmin,
}: {
  departmentId: string;
  job: ImportJob;
  fields: FieldOption[];
  isAdmin: boolean;
}) {
  const remap = useRemap(departmentId, job.id);
  const commit = useCommitImport(departmentId, job.id);
  const cancel = useCancelImport(departmentId, job.id);
  const template = useSaveTemplate(departmentId, job.id);
  const [confirm, setConfirm] = useState(false);
  const [overwrite, setOverwrite] = useState(false);
  const open = ["uploaded", "parsed", "mapped", "validated"].includes(job.status);
  const banner = phiBannerText(job.phi);
  const v = job.validation;

  async function onRemap(column: string, field: string | null) {
    try {
      await remap.mutateAsync({ [column]: field });
    } catch (err) {
      toast.error(errorText(err, "That mapping could not be applied"));
    }
  }

  async function onCommit() {
    try {
      const out = await commit.mutateAsync(overwrite);
      setConfirm(false);
      const skipped = out.skipped_dates.length
        ? ` ${out.skipped_dates.length} existing day${out.skipped_dates.length === 1 ? "" : "s"} skipped.`
        : "";
      toast.success(`${out.rows_committed} rows committed.${skipped}`, {
        action: { label: "Shift history", onClick: () => window.location.assign("/app/history") },
      });
    } catch (err) {
      toast.error(errorText(err, "Commit failed"));
    }
  }

  async function onRejected() {
    try {
      const blob = await downloadRejected(departmentId, job.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `rejected-${job.original_filename.replace(/\.[^.]+$/, "")}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(errorText(err, "Download failed"));
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Imports · review"
        title={job.original_filename}
        description="Check how each column maps, fix anything marked uncertain, then commit the valid rows."
        actions={
          <>
            <Button variant="outline" className="min-h-11" asChild>
              <Link href="/app/imports">Back to imports</Link>
            </Button>
            <StatusPill status={STATUS_KIND[job.status]} label={STATUS_LABEL[job.status]} />
          </>
        }
      />

      {job.parse?.error ? (
        <ErrorState title="The file could not be read" detail={job.parse.error} />
      ) : null}

      {banner ? (
        <div
          role="status"
          className="flex items-start gap-3 rounded-lg border border-status-warning-border bg-status-warning-bg p-4 text-status-warning"
        >
          <ShieldAlert className="mt-0.5 size-5 shrink-0" aria-hidden />
          <div>
            <p className="font-medium">Possible identifiers removed</p>
            <p className="text-sm">{banner} The removed values are not stored or shown.</p>
          </div>
        </div>
      ) : null}

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Readout
          label="Sheet"
          value={job.parse?.sheet ?? (job.parse?.file_type === "csv" ? "CSV" : "—")}
        />
        <Readout
          label="Header row"
          value={job.parse?.header_rows.map((r) => r + 1).join(" + ") || "—"}
        />
        <Readout label="Rows" value={String(job.parse?.rows ?? 0)} mono />
        <Readout
          label="Valid / invalid"
          value={`${v.valid_rows} / ${v.invalid_rows}`}
          mono
          tone={v.invalid_rows ? "warning" : "good"}
        />
      </dl>

      <section aria-labelledby="mapping" className="flex flex-col gap-3">
        <h2 id="mapping" className="engraved">
          Column mapping
        </h2>
        <Table>
          <TableCaption className="sr-only">Source columns and the fields they map to</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>Source column</TableHead>
              <TableHead>Sample values</TableHead>
              <TableHead>Maps to</TableHead>
              <TableHead>Method</TableHead>
              <TableHead>Confidence</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {job.columns.map((col) => (
              <TableRow key={col.column}>
                <TableCell className="font-medium">{col.column}</TableCell>
                <TableCell className="max-w-56 truncate font-mono text-13 text-muted-foreground">
                  {col.phi_flagged ? (
                    <span className="font-sans italic">Hidden (possible identifiers)</span>
                  ) : (
                    (col.samples ?? []).join(", ") || "—"
                  )}
                </TableCell>
                <TableCell>
                  <FieldPicker
                    column={col.column}
                    value={col.field}
                    suggestion={col.suggested_field ?? null}
                    fields={fields}
                    disabled={!open || remap.isPending}
                    onChange={(f) => onRemap(col.column, f)}
                  />
                </TableCell>
                <TableCell>
                  {col.method ? (
                    <span className="rounded-sm border px-1.5 py-0.5 text-xs font-medium">
                      {METHOD_LABEL[col.method]}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">Unmapped</span>
                  )}
                </TableCell>
                <TableCell>
                  {col.method ? (
                    col.uncertain ? (
                      <StatusPill
                        status="warning"
                        label={`Uncertain ${Math.round(col.confidence * 100)}%`}
                      />
                    ) : (
                      <span className="font-mono tabular-nums text-13">
                        {Math.round(col.confidence * 100)}%
                      </span>
                    )
                  ) : null}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {job.columns.some((c) => c.suggested_field) ? (
          <p className="text-13 text-muted-foreground">
            AI suggestions are shown but never applied. Pick the suggested field to accept it.
          </p>
        ) : null}
      </section>

      <ValidationErrors errors={v.errors} />
      <Preview rows={v.preview} fields={fields} />

      <div className="sticky bottom-0 flex flex-wrap items-center gap-2 border-t bg-background/95 py-3 backdrop-blur">
        <Button
          className="min-h-11"
          disabled={!open || v.valid_rows === 0 || commit.isPending}
          onClick={() => setConfirm(true)}
        >
          Commit {v.valid_rows} valid rows
        </Button>
        <Button
          variant="outline"
          className="min-h-11"
          disabled={!open || template.isPending}
          onClick={async () => {
            try {
              await template.mutateAsync();
              toast.success("Mapping saved. The next file with these columns maps itself.");
            } catch (err) {
              toast.error(errorText(err, "The template could not be saved"));
            }
          }}
        >
          Save mapping as template
        </Button>
        <Button
          variant="outline"
          className="min-h-11"
          disabled={v.invalid_rows === 0}
          onClick={onRejected}
        >
          <Download aria-hidden /> Rejected rows
        </Button>
        <Button
          variant="ghost"
          className="min-h-11"
          disabled={!open || cancel.isPending}
          onClick={async () => {
            await cancel.mutateAsync();
            toast.success("Import cancelled and the file deleted");
          }}
        >
          <X aria-hidden /> Cancel import
        </Button>
      </div>

      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Commit {v.valid_rows} rows as real data?</DialogTitle>
            <DialogDescription>
              Plans and approved shift logs are created for each valid day. Days that already have
              real data are skipped. The commit is recorded in the audit log.
            </DialogDescription>
          </DialogHeader>
          {isAdmin ? (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-4"
                checked={overwrite}
                onChange={(e) => setOverwrite(e.target.checked)}
              />
              Replace days that already have real data (department admin)
            </label>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm(false)}>
              Back
            </Button>
            <Button onClick={onCommit} disabled={commit.isPending}>
              Commit rows
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Readout({
  label,
  value,
  mono,
  tone,
}: {
  label: string;
  value: string;
  mono?: boolean;
  tone?: "good" | "warning";
}) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <dt className="engraved">{label}</dt>
      <dd
        className={cn(
          "mt-1 text-lg",
          mono && "font-mono tabular-nums",
          tone === "warning" && "text-status-warning",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

function FieldPicker({
  column,
  value,
  suggestion,
  fields,
  disabled,
  onChange,
}: {
  column: string;
  value: string | null;
  suggestion: string | null;
  fields: FieldOption[];
  disabled: boolean;
  onChange: (field: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const label = (name: string | null) =>
    name ? (fields.find((f) => f.name === name)?.label ?? name) : null;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          aria-label={`Field for column ${column}`}
          className="min-h-11 w-56 justify-between"
          disabled={disabled}
        >
          <span className={cn("truncate", !value && "text-muted-foreground")}>
            {label(value) ?? (suggestion ? `Suggested: ${label(suggestion)}` : "Leave out")}
          </span>
          <ChevronsUpDown className="size-4 opacity-60" aria-hidden />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0">
        <Command>
          <CommandInput placeholder="Search fields" />
          <CommandList>
            <CommandEmpty>No field matches.</CommandEmpty>
            <CommandGroup>
              <CommandItem
                value="leave out"
                onSelect={() => {
                  setOpen(false);
                  onChange(null);
                }}
              >
                Leave this column out
              </CommandItem>
              {fields.map((f) => (
                <CommandItem
                  key={f.name}
                  value={`${f.label} ${f.name}`}
                  onSelect={() => {
                    setOpen(false);
                    onChange(f.name);
                  }}
                >
                  <span className="flex flex-col">
                    <span>
                      {f.label}
                      {f.name === suggestion ? " (suggested)" : ""}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {f.description}
                      {f.unit ? ` · ${f.unit}` : ""}
                    </span>
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

function ValidationErrors({ errors }: { errors: ImportJob["validation"]["errors"] }) {
  const [column, setColumn] = useState<string>("all");
  const columns = useMemo(
    () => [...new Set(errors.map((e) => e.column ?? "row"))].sort(),
    [errors],
  );
  const shown = errors.filter((e) => column === "all" || (e.column ?? "row") === column);
  return (
    <section aria-labelledby="validation" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h2 id="validation" className="engraved">
          Validation
        </h2>
        {errors.length ? (
          <label className="flex items-center gap-2 text-sm">
            Column
            <select
              className="min-h-11 rounded-md border bg-background px-2"
              value={column}
              onChange={(e) => setColumn(e.target.value)}
            >
              <option value="all">All columns</option>
              {columns.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>
      {errors.length === 0 ? (
        <p className="text-sm text-muted-foreground">Every row passed validation.</p>
      ) : (
        <Table>
          <TableCaption className="sr-only">Validation errors by row and column</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead className="text-right">Row</TableHead>
              <TableHead>Column</TableHead>
              <TableHead>Value</TableHead>
              <TableHead>Message</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.slice(0, 200).map((e, i) => (
              <TableRow key={`${e.row}-${e.column}-${i}`}>
                <TableCell className="text-right font-mono tabular-nums">
                  {e.row === null ? "—" : e.row + 1}
                </TableCell>
                <TableCell>{e.column ?? "Whole row"}</TableCell>
                <TableCell className="font-mono text-13">{e.value ?? "—"}</TableCell>
                <TableCell>
                  {e.kind === "blocked" ? (
                    <StatusPill status="info" label="Cell blocked; row still imports" />
                  ) : (
                    e.message
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </section>
  );
}

function Preview({
  rows,
  fields,
}: {
  rows: ImportJob["validation"]["preview"];
  fields: FieldOption[];
}) {
  const cols = useMemo(() => {
    const seen = new Set<string>();
    for (const r of rows) for (const k of Object.keys(r.cells)) seen.add(k);
    return fields.map((f) => f.name).filter((n) => seen.has(n));
  }, [rows, fields]);
  if (!rows.length) return null;
  const label = (n: string) => fields.find((f) => f.name === n)?.label ?? n;
  return (
    <section aria-labelledby="preview" className="flex flex-col gap-3">
      <h2 id="preview" className="engraved">
        Preview (first {rows.length} rows)
      </h2>
      <p className="text-13 text-muted-foreground">
        Highlighted cells were normalized; hover or focus one to see the value in your file.
      </p>
      <TooltipProvider>
        <div className="overflow-x-auto rounded-lg border">
          <Table>
            <TableCaption className="sr-only">Transformed rows as they will be stored</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead className="text-right">Row</TableHead>
                {cols.map((c) => (
                  <TableHead key={c} className="whitespace-nowrap">
                    {label(c)}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.row}>
                  <TableCell className="text-right font-mono tabular-nums">{r.row + 1}</TableCell>
                  {cols.map((c) => {
                    const cell = r.cells[c];
                    if (!cell) return <TableCell key={c} />;
                    if (cell.hidden)
                      return (
                        <TableCell key={c} className="italic text-muted-foreground">
                          text (hidden)
                        </TableCell>
                      );
                    const text = cell.value === null ? "—" : String(cell.value);
                    return (
                      <TableCell key={c} className="font-mono text-13 tabular-nums">
                        {cell.changed ? (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span
                                tabIndex={0}
                                className="rounded-sm bg-status-info-bg px-1 text-status-info"
                                aria-label={`${text}, was ${cell.original}`}
                              >
                                {text}
                              </span>
                            </TooltipTrigger>
                            <TooltipContent>In your file: {cell.original}</TooltipContent>
                          </Tooltip>
                        ) : (
                          text
                        )}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </TooltipProvider>
    </section>
  );
}
