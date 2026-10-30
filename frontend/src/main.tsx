import { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import ChatWorkspace from "./ChatWorkspace";
import FyWorkspace, { EvalComparisonPanel } from "./FyWorkspace";
import { buildOverview, topicFor } from "./overview.mjs";
import { displayStatus } from "./document-state.mjs";
import Select from "./Select";
import {
  uploadBatch,
  type UploadProgress,
  type UploadResult,
} from "./upload.mjs";

type Document = {
  id: string;
  filename: string;
  kind: string;
  size_bytes: number;
  status: "queued" | "processing" | "ready" | "failed";
  generation_status?: "not_requested" | "generating" | "generated" | "failed";
  generation_error?: string | null;
  auto_generate?: boolean;
  created_at: number;
  attempts: number;
  error: string | null;
  validation: { page_count?: number; sheet_count?: number } | null;
  source_summary?: { warnings: string[] } | null;
};
type Batch = {
  count: number;
  bytes: number;
  stage: "uploading" | "confirming" | "complete" | "error";
  progress: UploadProgress;
  results: UploadResult[];
  error?: string;
};
type Connection = "loading" | "connected" | "offline";
type Filter = "all" | "processing" | "ready" | "failed";
type WorkspaceView = "library" | "data" | "source" | "qa" | "fy" | "eval";
type DataTab = "checked" | "review" | "issues" | "history";
type DataMode = "overview" | "details";
const api = import.meta.env.VITE_API_URL || "";
const statusLabels: Record<Document["status"] | "generating" | "generated", string> = {
  queued: "Queued",
  processing: "Processing",
  ready: "Source extracted",
  failed: "Needs attention",
  generating: "Generating",
  generated: "Generated",
};
const formatSize = (bytes: number) =>
  bytes < 1024 * 1024
    ? `${(bytes / 1024).toFixed(1)} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

type IconName =
  | "leaf"
  | "grid"
  | "upload"
  | "file"
  | "check"
  | "clock"
  | "alert"
  | "search"
  | "arrow"
  | "layers";
function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    leaf: (
      <>
        <path d="M20 4C12 4 5 7 5 14a5 5 0 0 0 5 5c7 0 10-7 10-15Z" />
        <path d="M4 21c2-5 6-9 12-12" />
      </>
    ),
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </>
    ),
    upload: (
      <>
        <path d="M12 16V3m-5 5 5-5 5 5" />
        <path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
      </>
    ),
    file: (
      <>
        <path d="M6 3h8l4 4v14H6z" />
        <path d="M14 3v5h4M9 13h6M9 17h6" />
      </>
    ),
    check: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="m8 12 3 3 5-6" />
      </>
    ),
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    alert: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v6m0 4h.01" />
      </>
    ),
    search: (
      <>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 4 4" />
      </>
    ),
    arrow: (
      <>
        <path d="M5 12h14m-5-5 5 5-5 5" />
      </>
    ),
    layers: (
      <>
        <path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5" />
      </>
    ),
  };
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  );
}

function Sidebar({
  count,
  view,
  navigate,
}: {
  count: number;
  view: WorkspaceView;
  navigate: (view: WorkspaceView) => void;
}) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-icon">
          <Icon name="leaf" size={23} />
        </span>
        <div>
          <strong>verdant</strong>
          <small>SUSTAINABILITY WORKSPACE</small>
        </div>
      </div>
      <div className="side-section">WORKSPACE</div>
      <nav className="side-nav" aria-label="Workspace navigation">
        {(
          [
            ["library", "Document library", "grid"],
            ["qa", "Ask your documents", "search"],
            ["fy", "Financial year", "clock"],
            ["eval", "Evaluation", "check"],
            ["data", "Reported data", "layers"],
            ["source", "Source explorer", "file"],
          ] as const
        ).map(([target, label, icon]) => (
          <button
            key={target}
            className={view === target ? "side-active" : "side-link"}
            aria-current={view === target ? "page" : undefined}
            onClick={() => navigate(target)}
          >
            <Icon name={icon} size={18} />
            <span>{label}</span>
            {target === "library" && <b>{count}</b>}
          </button>
        ))}
      </nav>
      <div className="side-footer">
        <span className="side-dot" /> Local workspace
      </div>
    </aside>
  );
}

function Summary({ docs }: { docs: Document[] }) {
  const count = (status: ReturnType<typeof displayStatus>) =>
    docs.filter((d) => displayStatus(d) === status).length;
  const items: {
    label: string;
    value: number;
    detail: string;
    icon: IconName;
    tone: string;
  }[] = [
    {
      label: "Documents",
      value: docs.length,
      detail: `${countKind(docs, "pdf")} PDF · ${countKind(docs, "xlsx")} XLSX`,
      icon: "file",
      tone: "green",
    },
    {
      label: "Generating",
      value: count("queued") + count("processing") + count("generating"),
      detail: "Reading source and generating data",
      icon: "clock",
      tone: "blue",
    },
    {
      label: "Generated",
      value: count("generated"),
      detail: "OpenAI generation complete",
      icon: "check",
      tone: "emerald",
    },
    {
      label: "Needs attention",
      value: count("failed"),
      detail: "Review and retry",
      icon: "alert",
      tone: "amber",
    },
  ];
  return (
    <section className="summary" aria-label="Document overview">
      {items.map((item) => (
        <div className="stat" key={item.label}>
          <div className="stat-top">
            <span>{item.label}</span>
            <span className={`stat-icon ${item.tone}`}>
              <Icon name={item.icon} size={18} />
            </span>
          </div>
          <strong>{item.value}</strong>
          <small>{item.detail}</small>
        </div>
      ))}
    </section>
  );
}
function countKind(docs: Document[], kind: string) {
  return docs.filter((d) => d.kind === kind).length;
}

function UploadPanel({
  busy,
  notice,
  batch,
  docs,
  onUpload,
}: {
  busy: boolean;
  notice: string;
  batch: Batch | null;
  docs: Document[];
  onUpload: (files: FileList | File[]) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  return (
    <section className="upload-card" aria-labelledby="upload-title">
      <div className="upload-intro">
        <div className="upload-title-icon">
          <Icon name="upload" size={21} />
        </div>
        <div>
          <div className="section-kicker">ADD DOCUMENTS</div>
          <h2 id="upload-title">Bring your sources in</h2>
          <p>Upload bills, workbooks, and policies. OpenAI generates data automatically in the background; API charges may apply.</p>
        </div>
      </div>
      <div
        className={`drop ${drag ? "drag" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          if (!busy) setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          if (!busy) onUpload(e.dataTransfer.files);
        }}
      >
        <span className="drop-icon">
          <Icon name="upload" size={21} />
        </span>
        <div className="drop-copy">
          <strong>Drag and drop your files here</strong>
          <p>PDF or XLSX · up to 25 MB each · maximum 10 files</p>
        </div>
        <button
          className="primary-button"
          disabled={busy}
          onClick={() => input.current?.click()}
        >
          {busy ? "Uploading…" : "Browse files"}
          <Icon name="arrow" size={16} />
        </button>
        <input
          ref={input}
          type="file"
          accept=".pdf,.xlsx"
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files) onUpload(e.target.files);
            e.target.value = "";
          }}
        />
      </div>
      {batch && <BatchProgress batch={batch} docs={docs} />}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
    </section>
  );
}

function BatchProgress({ batch, docs }: { batch: Batch; docs: Document[] }) {
  const progress =
    typeof batch.progress === "object" && batch.progress !== null
      ? batch.progress
      : null;
  const percent =
    progress && progress.total > 0
      ? Math.min(100, Math.round((progress.loaded / progress.total) * 100))
      : null;
  const stage =
    batch.stage === "uploading"
      ? "Uploading batch"
      : batch.stage === "confirming"
        ? "Transfer complete · waiting for server confirmation"
        : batch.stage === "complete"
          ? "Upload results"
          : "Upload interrupted";
  const added = batch.results.filter((r) => !r.error && !r.duplicate).length;
  const duplicates = batch.results.filter(
    (r) => !r.error && r.duplicate,
  ).length;
  const failed = batch.results.filter((r) => r.error);
  return (
    <div className="batch-panel">
      <div className="batch-heading">
        <div>
          <strong>{stage}</strong>
          <p>
            {batch.count} {batch.count === 1 ? "file" : "files"} ·{" "}
            {formatSize(batch.bytes)} of selected files
          </p>
        </div>
        {batch.stage === "uploading" && percent !== null && (
          <strong>{percent}%</strong>
        )}
      </div>
      {(batch.stage === "uploading" || batch.stage === "confirming") && (
        <>
          <progress
            aria-label="Batch upload progress"
            max={100}
            {...(percent !== null || batch.stage === "confirming"
              ? { value: batch.stage === "confirming" ? 100 : percent! }
              : {})}
          />
          <p className="batch-help">
            {progress && batch.stage === "uploading"
              ? `${formatSize(progress.loaded)} of ${formatSize(progress.total)} transferred (includes request overhead).`
              : batch.stage === "confirming"
                ? "The server is registering your files."
                : "Transfer size unavailable; upload is in progress."}{" "}
            OpenAI generation starts automatically after the source is read.
          </p>
        </>
      )}
      {batch.stage === "complete" && (
        <>
          <p className="batch-help">
            {added} added · {duplicates} already in library · {failed.length}{" "}
            failed. OpenAI generation continues in the document library.
          </p>
          <ul className="batch-results">
            {batch.results.map((result, index) => {
              const current = docs.find((d) => d.id === result.document?.id);
              const status = current ? displayStatus(current) : result.document ? displayStatus(result.document) : undefined;
              return (
                <li key={`${index}-${result.filename}`}>
                  <span title={result.filename}>{result.filename}</span>
                  <span className={result.error ? "result-error" : "result-ok"}>
                    {result.error ||
                      `${result.duplicate ? "Already in library" : "Added"}${status ? ` · ${statusLabels[status]}` : ""}`}
                  </span>
                </li>
              );
            })}
          </ul>
        </>
      )}
      {batch.error && (
        <p className="batch-error" role="alert">
          {batch.error}
        </p>
      )}
    </div>
  );
}

function Library({
  docs,
  retry,
  inspect,
  openFacts,
}: {
  docs: Document[];
  retry: (id: string) => void;
  inspect: (document: Document) => void;
  openFacts: (document: Document) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const visible = docs.filter(
    (d) =>
      (filter === "all" ||
        (filter === "processing"
          ? ["processing", "queued", "generating"].includes(displayStatus(d))
          : filter === "ready" ? ["ready", "generated"].includes(displayStatus(d))
          : displayStatus(d) === filter)) &&
      d.filename.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()),
  );
  const filters: [Filter, string][] = [
    ["all", "All documents"],
    ["processing", "Generating"],
    ["ready", "Generated"],
    ["failed", "Needs attention"],
  ];
  return (
    <section className="library" aria-labelledby="library-title">
      <div className="library-heading">
        <div>
          <div className="section-kicker">YOUR DOCUMENTS</div>
          <h2 id="library-title">
            Document library <span>{docs.length}</span>
          </h2>
          <p>Monitor the status of your uploaded source files.</p>
        </div>
        <label className="search">
          <Icon name="search" size={17} />
          <span className="sr-only">Search by filename</span>
          <input
            type="search"
            placeholder="Search documents"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
      </div>
      <div className="filters" aria-label="Filter documents by status">
        {filters.map(([value, label]) => (
          <button
            key={value}
            className={filter === value ? "selected" : ""}
            aria-pressed={filter === value}
            onClick={() => setFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">DOCUMENT</th>
              <th scope="col">DATE ADDED</th>
              <th scope="col">STATUS</th>
              <th scope="col">ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((d) => (
              <tr key={d.id}>
                <td>
                  <div className="file">
                    <span className={`file-icon ${d.kind}`}>
                      <Icon name="file" size={19} />
                    </span>
                    <div className="file-detail">
                      <strong title={d.filename}>{d.filename}</strong>
                      <small>
                        {d.kind.toUpperCase()} · {formatSize(d.size_bytes)}
                        {d.validation?.page_count
                          ? ` · ${d.validation.page_count} ${d.validation.page_count === 1 ? "page" : "pages"}`
                          : d.validation?.sheet_count
                            ? ` · ${d.validation.sheet_count} ${d.validation.sheet_count === 1 ? "sheet" : "sheets"}`
                            : ""}
                      </small>
                      {d.error && (
                        <small className="row-error">{d.error}</small>
                      )}
                      {d.generation_error && <small className="row-error">{d.generation_error}</small>}
                    </div>
                  </div>
                </td>
                <td className="date">
                  {new Date(d.created_at * 1000).toLocaleDateString(undefined, {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                </td>
                <td>
                  <span className={`badge ${displayStatus(d)}`}>
                    <i />
                    {statusLabels[displayStatus(d)]}
                  </span>
                  {!!d.source_summary?.warnings.length && <span className="source-warning-label" title={d.source_summary.warnings.join("\n")}>
                    <Icon name="alert" size={12} /> Source warnings
                  </span>}
                </td>
                <td><div className="library-actions">
                  {d.status === "ready" && (
                    <button className="library-action source-action" onClick={() => inspect(d)} aria-label={`Inspect source for ${d.filename}`}>
                      <Icon name="file" size={14} /> Source
                    </button>
                  )}
                  {d.status === "ready" && (
                    <button className="library-action data-action" onClick={() => openFacts(d)} aria-label={`View data for ${d.filename}`}>
                      View data <Icon name="arrow" size={14} />
                    </button>
                  )}
                  {displayStatus(d) === "failed" && (
                    <button
                      className="library-action source-action"
                      aria-label={`Retry ${d.filename}`}
                      onClick={() => retry(d.id)}
                    >
                      Retry <Icon name="arrow" size={14} />
                    </button>
                  )}
                </div></td>
              </tr>
            ))}
          </tbody>
        </table>
        {visible.length === 0 && (
          <div className="empty">
            <span>
              <Icon name="file" size={24} />
            </span>
            <strong>
              {docs.length ? "No matching documents" : "Your library is ready"}
            </strong>
            <p>
              {docs.length
                ? "Try another search or status filter."
                : "Add a PDF or spreadsheet to get started."}
            </p>
          </div>
        )}
      </div>
      <div className="library-footer">
        Showing {visible.length} of {docs.length} documents{" "}
        <span>Updated automatically</span>
      </div>
    </section>
  );
}

type SourceCell = {
  coordinate: string;
  type: string;
  value: unknown;
  formula: string | null;
  cached_value: unknown;
  number_format: string;
};
type Sources = {
  kind: string;
  version: number;
  summary: { warnings: string[] };
  units: { index: number; label: string }[];
  unit?: {
    index: number;
    label: string;
    text?: string;
    reading_blocks?: { label: string; bbox: number[]; text: string }[] | null;
    cells?: SourceCell[];
    total_cells?: number;
    offset?: number;
  };
};

function SourceInspector({
  document,
  onClose,
  initialUnit = 1,
}: {
  document: Document;
  onClose: () => void;
  initialUnit?: number;
}) {
  const [source, setSource] = useState<Sources | null>(null);

  const [unit, setUnit] = useState(initialUnit);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    setSource(null);
    setUnit(initialUnit);
    setOffset(0);
  }, [document.id, initialUnit]);
  useEffect(() => {
    const controller = new AbortController();
    setSource(null);
    setError("");
    fetch(
      `${api}/api/documents/${document.id}/sources?unit=${unit}&offset=${offset}&limit=100`,
      { signal: controller.signal },
    )
      .then(async (response) => {
        if (!response.ok) throw Error("Could not load source content.");
        return response.json();
      })
      .then(setSource)
      .catch((error) => {
        if (error.name !== "AbortError") setError(error.message);
      });
    return () => controller.abort();
  }, [document.id, unit, offset]);
  const current =
    source?.unit?.index === unit &&
    (source.kind !== "xlsx" || source.unit.offset === offset)
      ? source.unit
      : undefined;
  const showValue = (value: unknown) =>
    value === null || value === undefined ? "—" : String(value);
  return (
    <section className="source-panel" aria-labelledby="source-title">
      <div className="source-heading">
        <div>
          <div className="section-kicker">SOURCE INSPECTOR</div>
          <h2 id="source-title">{document.filename}</h2>
          <p>
            Original source content and locations · extraction version{" "}
            {source?.version || 1}
          </p>
        </div>
        <button className="source-button" onClick={onClose}>
          Close
        </button>
      </div>
      <p className="source-disclaimer">
        Source content is not a verified sustainability metric. Formula caches
        may be missing or stale; formulas are not recalculated.
      </p>
      {error && (
        <p className="batch-error" role="alert">
          {error}
        </p>
      )}
      {!source && !error && <p className="batch-help">Loading source…</p>}
      {source && (
        <>
          {source.summary.warnings.length > 0 && (
            <ul className="source-warnings">
              {source.summary.warnings.map((warning, index) => (
                <li key={index}>{warning}</li>
              ))}
            </ul>
          )}
          <div className="source-controls">
            <label>
              {source.kind === "pdf" ? "Page" : "Sheet"}
              <Select label={source.kind === "pdf" ? "Page" : "Sheet"}
                value={String(unit)} options={source.units.map((item) => ({ value: String(item.index), label: item.label }))}
                onChange={(value) => {
                  setUnit(Number(value));
                  setOffset(0);
                }}
              />
            </label>
          </div>
          {current && source.kind === "pdf" && (
            <div className="source-text">
              <strong>{current.label}</strong>
              {current.reading_blocks?.length ? (
                <>
                  <p>
                    Detected reading columns; bounding boxes are PDF
                    coordinates.
                  </p>
                  {current.reading_blocks.map((block, i) => (
                    <div key={i}>
                      <strong>
                        Block {i + 1} · {block.label} · [
                        {block.bbox.map((n) => n.toFixed(1)).join(", ")}]
                      </strong>
                      <pre>{block.text}</pre>
                    </div>
                  ))}
                  <details>
                    <summary>Original page text</summary>
                    <pre>{current.text}</pre>
                  </details>
                </>
              ) : (
                <pre>{current.text || "No extractable text on this page."}</pre>
              )}
            </div>
          )}
          {current && source.kind === "xlsx" && (
            <>
              <div className="source-table">
                <table>
                  <thead>
                    <tr>
                      <th>Cell</th>
                      <th>Type</th>
                      <th>Value</th>
                      <th>Formula</th>
                      <th>Cached value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {current.cells?.map((cell) => (
                      <tr key={cell.coordinate}>
                        <td>{cell.coordinate}</td>
                        <td>
                          {cell.type} · {cell.number_format}
                        </td>
                        <td>{showValue(cell.value)}</td>
                        <td>{showValue(cell.formula)}</td>
                        <td>{showValue(cell.cached_value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!current.total_cells && (
                  <p className="batch-help">No nonempty cells in this sheet.</p>
                )}
              </div>
              <div className="source-pagination">
                <button
                  className="source-button"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - 100))}
                >
                  Previous
                </button>
                <span>
                  {current.total_cells
                    ? `${offset + 1}–${Math.min(offset + 100, current.total_cells)} of ${current.total_cells} cells`
                    : "0 cells"}
                </span>
                <button
                  className="source-button"
                  disabled={offset + 100 >= (current.total_cells || 0)}
                  onClick={() => setOffset(offset + 100)}
                >
                  Next
                </button>
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}

type FactEvidence = {
  unit_index: number;
  quote: string;
  cells: string[];
  located_locally?: boolean;
  reference_id?: string;
};
type ReportedFact = {
  organization: string | null;
  label: string;
  source_label: string;
  method?: string;
  fact_index?: number;
  recovery_audit?: {
    field: string;
    original_ids: string[];
    recovered_ids: string[];
    reason: string;
  }[];
  value: string;
  unit: string | null;
  period: string | null;
  currency: string | null;
  evidence: FactEvidence;
  context_evidence: FactEvidence[];
};
type FactsState = {
  status: "not_requested" | "queued" | "processing" | "ready" | "failed";
  provider?: string;
  error?: string | null;
  segments?: {
    segment_id: string;
    status: string;
    attempts: number;
    error: string | null;
  }[];
  output?: {
    model: string;
    provider?: string;
    operational_coverage?: string;
    completed_segments?: number;
    total_segments?: number;
    completed_target_records?: number;
    total_target_records?: number;
    failed_segments?: number;
    proposed_result?: unknown;
    segment_outputs?: { proposed_result?: unknown }[];
    validator_version?: string;
    result: {
      organization: string | null;
      document_type: string;
      coverage: "complete" | "partial";
      coverage_note: string;
      facts: ReportedFact[];
      review_candidates?: (ReportedFact & { review_reason: string })[];
      warnings: string[];
      review_issues?: {
        fact_index: number | null;
        field: string;
        proposed: unknown;
        reason: string;
      }[];
      rejected_candidates?: {
        fact_index: number;
        reason: string;
        candidate: unknown;
      }[];
    };
  } | null;
};

function ReportedDetailCard({ fact, review = false, kind, onEvidence }: {
  fact: ReportedFact & { review_reason?: string };
  review?: boolean;
  kind: string;
  onEvidence: (unit: number) => void;
}) {
  const location = (evidence: FactEvidence) => `${kind === "pdf" ? "Page" : "Sheet"} ${evidence.unit_index}${evidence.cells.length ? ` · ${evidence.cells.join(", ")}` : ""}`;
  const evidenceKey = (evidence: FactEvidence) => JSON.stringify([evidence.unit_index, evidence.reference_id, evidence.cells, evidence.quote, evidence.located_locally]);
  const contexts = fact.context_evidence.filter((item, index, all) => evidenceKey(item) !== evidenceKey(fact.evidence)
    && all.findIndex((other) => evidenceKey(other) === evidenceKey(item)) === index);
  const origin = fact.method === "deterministic_table_fact" || fact.method === "deterministic_table_candidate"
    ? "System-mapped label" : fact.method === "local_exact_reference_recovery" ? "Recovered references" : "AI-proposed label";
  const labelRepeatsValue = fact.label.trim() === fact.value.trim();
  return <article className={`reported-card ${review ? "needs-review" : ""}`}>
    <header className="reported-card-head">
      <span className="reported-origin">{origin}</span>
      <span className={`reported-status ${review ? "review" : "checked"}`}><i />{review ? "Needs review" : "Checked"}</span>
    </header>
    {!labelRepeatsValue && <h3 className="reported-label">{fact.label}</h3>}
    <div className={`reported-value ${fact.value.length > 70 || labelRepeatsValue ? "is-statement" : ""}`} role={labelRepeatsValue ? "heading" : undefined} aria-level={labelRepeatsValue ? 3 : undefined}>
      {fact.value}
      {(fact.unit || fact.currency) && <small>{[fact.unit, fact.currency].filter(Boolean).join(" · ")}</small>}
    </div>
    <dl className="reported-metadata">
      <div><dt>Organization</dt><dd className={!fact.organization ? "not-stated" : ""}>{fact.organization || "Not identified"}</dd></div>
      <div><dt>Period</dt><dd className={!fact.period ? "not-stated" : ""}>{fact.period || "Not specified"}</dd></div>
    </dl>
    {review && <p className="reported-review-note"><Icon name="alert" size={14} /><span>{fact.review_reason || "The relationship between the label and value needs review. This is not an accepted fact."}</span></p>}
    <div className="reported-source-row"><span><Icon name="file" size={14} />{location(fact.evidence)}</span>
      <button onClick={() => onEvidence(fact.evidence.unit_index)} aria-label={`View source for ${fact.label}`}>View source <Icon name="arrow" size={14} /></button>
    </div>
    <details className="reported-evidence">
      <summary><span>Evidence &amp; context</span><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m7 10 5 5 5-5" /></svg></summary>
      <div className="reported-evidence-body">
        <div className="reported-evidence-label">Exact source label</div><p>{fact.source_label}</p>
        <div className="reported-evidence-label">Source excerpt {fact.evidence.reference_id && <code>{fact.evidence.reference_id}</code>}</div>
        <blockquote>{fact.evidence.quote}</blockquote>
        {contexts.map((item, index) => <div className="reported-context" key={evidenceKey(item)}>
          <div className="reported-evidence-label">{item.located_locally ? "Locally located label" : `Supporting context ${index + 1}`}</div>
          <blockquote>{item.quote}</blockquote>
          <button onClick={() => onEvidence(item.unit_index)}>Open {location(item)} <Icon name="arrow" size={12} /></button>
        </div>)}
        {fact.recovery_audit?.map((entry, index) => <div className="reported-recovery" key={index}>
          <strong>Reference recovery · {entry.field}</strong><p>{entry.original_ids.join(", ")} → {entry.recovered_ids.join(", ")}</p><p>{entry.reason}</p>
        </div>)}
      </div>
    </details>
  </article>;
}

function DataOverview({
  result,
  state,
  onDrill,
  onEvidence,
}: {
  result: NonNullable<FactsState["output"]>["result"];
  state: FactsState;
  onDrill: (tab: DataTab, topic?: string) => void;
  onEvidence: (unit: number) => void;
}) {
  const checked = result.facts;
  const review = result.review_candidates || [];
  const rejected = result.rejected_candidates || [];
  const issues = result.review_issues || [];
  const total = checked.length + review.length + rejected.length;
  const overview = buildOverview(checked, review);
  const slices = [
    {
      label: "Checked",
      count: checked.length,
      color: "#23845e",
      tab: "checked" as DataTab,
    },
    {
      label: "Needs review",
      count: review.length,
      color: "#c99543",
      tab: "review" as DataTab,
    },
    {
      label: "Rejected",
      count: rejected.length,
      color: "#b9c8c1",
      tab: "issues" as DataTab,
    },
  ];
  let offset = 0;
  const diameter = 2 * Math.PI * 44;
  const maxTopic = Math.max(1, ...overview.topics.map((item) => item.count));
  return (
    <div className="overview">
      <div className="overview-intro">
        <div>
          <div className="section-kicker">DOCUMENT OVERVIEW</div>
          <h2>A clearer view of your sources</h2>
          <p>
            Counts are calculated from saved results. Highlighted values are
            shown as reported; review their evidence.
          </p>
        </div>
        <span className="overview-chip">
          <span /> LIVE DOCUMENT DATA
        </span>
      </div>
      <div className="overview-stats">
        <button onClick={() => onDrill("checked")}>
          <span className="overview-stat-icon mint">
            <Icon name="check" size={17} />
          </span>
          <span className="overview-stat-label">Checked against source</span>
          <strong>{checked.length}</strong>
          <small>
            Evidence checks passed <span>↗</span>
          </small>
        </button>
        <button onClick={() => onDrill("review")}>
          <span className="overview-stat-icon sand">
            <Icon name="clock" size={17} />
          </span>
          <span className="overview-stat-label">Needs review</span>
          <strong>{review.length}</strong>
          <small>
            Associations to confirm <span>↗</span>
          </small>
        </button>
        <button onClick={() => onDrill("issues")}>
          <span className="overview-stat-icon slate">
            <Icon name="alert" size={17} />
          </span>
          <span className="overview-stat-label">Rejected proposals</span>
          <strong>{rejected.length}</strong>
          <small>
            {issues.length} separate review issues <span>↗</span>
          </small>
        </button>
        <div className="coverage-stat">
          <span className="overview-stat-icon blue">
            <Icon name="layers" size={17} />
          </span>
          <span className="overview-stat-label">Segments completed</span>
          <strong>
            {state.output?.total_segments
              ? `${state.output.completed_segments ?? 0}/${state.output.total_segments}`
              : "—"}
          </strong>
          <small>
            {state.output?.total_segments
              ? "Segments processed"
              : "No segment plan available"}
          </small>
        </div>
      </div>
      <section className="highlight-section">
        <div className="highlights-head">
          <div>
            <span className="section-kicker">FROM THE SOURCE</span>
            <h3>Reported highlights</h3>
            <p>Selected values, shown as reported; no totals are calculated.</p>
          </div>
          <button className="overview-link" onClick={() => onDrill("checked")}>
            View all details <Icon name="arrow" size={15} />
          </button>
        </div>
        {overview.highlights.length ? (
          <div className="highlight-grid">
            {overview.highlights.map(({ fact, status, kind }, i) => (
              <article className="highlight-card" key={i}>
                <div className="highlight-top">
                  <span className="section-kicker">{kind.toUpperCase()}</span>
                  <span className={`highlight-badge ${status}`}>
                    {status === "checked" ? "Source checked" : "Needs review"}
                  </span>
                </div>
                <strong className="highlight-value">{fact.value}</strong>
                <span className="highlight-unit">
                  {[fact.unit, fact.currency].filter(Boolean).join(" · ") ||
                    "Unit not specified"}
                </span>
                <p>
                  {fact.label} ·{" "}
                  {fact.organization || "Organization not identified"}
                  {fact.period
                    ? ` · ${fact.period}`
                    : " · Period not specified"}
                </p>
                <button onClick={() => onEvidence(fact.evidence.unit_index)}>
                  View source <Icon name="arrow" size={14} />
                </button>
              </article>
            ))}
          </div>
        ) : overview.commitments.length ? (
          <div className="commitment-preview">
            <span className="overview-stat-icon mint">
              <Icon name="file" size={17} />
            </span>
            <div>
              <strong>
                {overview.commitments.length} policy or quality proposals
              </strong>
              <p>
                {overview.commitments[0].fact.organization ||
                  "Organization not identified"}{" "}
                ·{" "}
                {overview.commitments[0].status === "checked"
                  ? "Source checked"
                  : "Needs review"}
              </p>
              <p>{overview.commitments[0].fact.value}</p>
              <button
                onClick={() =>
                  onEvidence(overview.commitments[0].fact.evidence.unit_index)
                }
              >
                View source <Icon name="arrow" size={14} />
              </button>
            </div>
          </div>
        ) : (
          <div className="highlights-empty">
            No clearly identified reported numeric highlights are available for
            this document.
          </div>
        )}
      </section>
      <div className="overview-grid">
        <section className="insight-card distribution">
          <div className="insight-head">
            <div>
              <span className="section-kicker">REVIEW PIPELINE</span>
              <h3>Result distribution</h3>
              <p>Current stored category counts, not a quality score</p>
            </div>
            <span className="insight-icon">
              <Icon name="grid" size={16} />
            </span>
          </div>
          <div className="distribution-body">
            <div className="donut-wrap">
              <svg
                viewBox="0 0 120 120"
                role="img"
                aria-label={`Result item counts: ${checked.length} checked, ${review.length} need review, ${rejected.length} rejected`}
              >
                <circle
                  cx="60"
                  cy="60"
                  r="44"
                  fill="none"
                  stroke="#edf2ee"
                  strokeWidth="11"
                />
                {total > 0 &&
                  slices.map((slice) => {
                    const length = (diameter * slice.count) / total;
                    const current = offset;
                    offset += length;
                    return (
                      <circle
                        key={slice.label}
                        cx="60"
                        cy="60"
                        r="44"
                        fill="none"
                        stroke={slice.color}
                        strokeWidth="11"
                        strokeDasharray={`${length} ${diameter - length}`}
                        strokeDashoffset={-current}
                        transform="rotate(-90 60 60)"
                      />
                    );
                  })}
              </svg>
              <div className="donut-center">
                <strong>{total}</strong>
                <span>RESULT ITEMS</span>
              </div>
            </div>
            <div className="distribution-legend">
              {slices.map((slice) => (
                <button key={slice.label} onClick={() => onDrill(slice.tab)}>
                  <span
                    className="legend-dot"
                    style={{ background: slice.color }}
                  />
                  <span>{slice.label}</span>
                  <strong>{slice.count}</strong>
                  <span className="legend-arrow">↗</span>
                </button>
              ))}
            </div>
          </div>
          <div className="insight-footer">
            Review issues are tracked separately from rejected proposals.
          </div>
        </section>
        <section className="insight-card topics-card">
          <div className="insight-head">
            <div>
              <span className="section-kicker">AT A GLANCE</span>
              <h3>Proposal topics</h3>
              <p>Label-based categories · counts, not impact</p>
            </div>
            <span className="insight-icon">
              <Icon name="layers" size={16} />
            </span>
          </div>
          {overview.topics.length ? (
            <div className="topic-list">
              {overview.topics.map((item, index) => (
                <button
                  key={item.name}
                  onClick={() =>
                    onDrill(
                      checked.some((fact) => topicFor(fact) === item.name)
                        ? "checked"
                        : "review",
                      item.name,
                    )
                  }
                >
                  <span className="topic-label">
                    <span className={`topic-dot topic-${index % 4}`} />
                    {item.name}
                  </span>
                  <span className="topic-track">
                    <span
                      style={{ width: `${(item.count / maxTopic) * 100}%` }}
                    />
                  </span>
                  <strong>{item.count}</strong>
                </button>
              ))}
            </div>
          ) : (
            <div className="insight-empty">
              No checked or review proposals to categorize.
            </div>
          )}
          <div className="insight-footer">
            Categories are approximate and use proposal labels.
          </div>
        </section>
      </div>
      {overview.meterPair && (
        <section className="meter-card">
          <div className="insight-head">
            <div>
              <span className="section-kicker">FROM THE SOURCE</span>
              <h3>Reported reading values</h3>
              <p>
                Individual reported values · {overview.meterPair[0].fact.unit}
              </p>
            </div>
            <span className="insight-icon">
              <Icon name="file" size={16} />
            </span>
          </div>
          <div className="meter-content">
            <svg
              viewBox="0 0 240 122"
              role="img"
              aria-label={`Reported reading values ${overview.meterPair[0].fact.value} and ${overview.meterPair[1].fact.value}, ${overview.meterPair[0].fact.unit}`}
            >
              {overview.meterPair.map((item, i) => {
                const max = Math.max(
                  ...overview.meterPair!.map((value) => value.numeric),
                  1,
                );
                const height = (item.numeric / max) * 78;
                return (
                  <g key={i}>
                    <rect
                      x={i === 0 ? 55 : 145}
                      y={104 - height}
                      width="39"
                      height={height}
                      rx="5"
                      fill={i === 0 ? "#a4cfaa" : "#3a9567"}
                    />
                    <text
                      x={i === 0 ? 74.5 : 164.5}
                      y="118"
                      textAnchor="middle"
                      fontSize="9"
                      fill="#829c89"
                    >
                      {`Reading ${i + 1}`}
                    </text>
                  </g>
                );
              })}
            </svg>
            <div className="meter-readings">
              {overview.meterPair.map((item, i) => (
                <div key={i}>
                  <span>
                    {item.fact.label} ·{" "}
                    {item.status === "checked"
                      ? "Source checked"
                      : "Needs review"}
                  </span>
                  <strong>
                    {item.fact.value} <small>{item.fact.unit}</small>
                  </strong>
                  <p>{item.fact.period || "Period not specified"}</p>
                  <button
                    onClick={() => onEvidence(item.fact.evidence.unit_index)}
                  >
                    View source <Icon name="arrow" size={14} />
                  </button>
                </div>
              ))}
            </div>
          </div>
          <div className="insight-footer">
            Meter identity is not established; no change or consumption is
            calculated.
          </div>
        </section>
      )}
    </div>
  );
}

function FactsPanel({
  document,
  onClose,
  onEvidence,
  tab,
  setTab,
  search,
  setSearch,
  page,
  setPage,
  mode,
  setMode,
  topic,
  setTopic,
}: {
  document: Document;
  onClose: () => void;
  onEvidence: (unit: number) => void;
  tab: DataTab;
  setTab: (tab: DataTab) => void;
  search: string;
  setSearch: (search: string) => void;
  page: number;
  setPage: (page: number) => void;
  mode: DataMode;
  setMode: (mode: DataMode) => void;
  topic: string;
  setTopic: (topic: string) => void;
}) {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [plan, setPlan] = useState<{ segments: number } | null>(null);
  const [history, setHistory] = useState<
    {
      id: string;
      archived_at: number;
      job: {
        status: string;
        provider?: string;
        model?: string;
        audit?: { action: string; validator_version: string };
        prompt_version: string;
        result_json: string | null;
      };
    }[]
  >([]);
  const [state, setState] = useState<FactsState | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const sending = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${api}/api/documents/${document.id}/facts/history`, {
      signal: controller.signal,
    })
      .then((response) => (response.ok ? response.json() : { runs: [] }))
      .then((data) => setHistory(data.runs))
      .catch(() => {});
    fetch(`${api}/api/documents/${document.id}/facts/plan`, {
      signal: controller.signal,
    })
      .then((r) => (r.ok ? r.json() : null))
      .then(setPlan)
      .catch(() => {});
    fetch(`${api}/api/facts/config`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw Error();
        return response.json();
      })
      .then((data) => setConfigured(data.configured))
      .catch((e) => {
        if (e.name !== "AbortError")
          setError("Could not load OpenAI configuration.");
      });
    const refresh = () =>
      fetch(`${api}/api/documents/${document.id}/facts`, {
        signal: controller.signal,
      })
        .then((response) => {
          if (!response.ok) throw Error();
          return response.json();
        })
        .then(setState)
        .catch((e) => {
          if (e.name !== "AbortError")
            setError("Could not load fact extraction status.");
        });
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [document.id]);
  async function requestFacts() {
    if (sending.current) return;
    sending.current = true;
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(
        `${api}/api/documents/${document.id}/facts`,
        { method: "POST" },
      );
      const data = await response.json();
      if (!response.ok)
        throw Error(data.detail || "Could not request extraction.");
      setState(data);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not request extraction.",
      );
    } finally {
      sending.current = false;
      setSubmitting(false);
    }
  }
  async function recheck() {
    if (sending.current) return;
    sending.current = true;
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(
        `${api}/api/documents/${document.id}/facts/revalidate`,
        { method: "POST" },
      );
      const data = await response.json();
      if (!response.ok)
        throw Error(data.detail || "Could not recheck saved candidates.");
      setState(data);
      const historyResponse = await fetch(
        `${api}/api/documents/${document.id}/facts/history`,
      );
      if (historyResponse.ok) setHistory((await historyResponse.json()).runs);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not recheck saved candidates.",
      );
    } finally {
      sending.current = false;
      setSubmitting(false);
    }
  }
  const result = state?.output?.result;
  const pending = state?.status === "queued" || state?.status === "processing";
  const query = search.trim().toLocaleLowerCase();
  const matches = (value: unknown) =>
    !query || JSON.stringify(value).toLocaleLowerCase().includes(query);
  const matchesTopic = (fact: ReportedFact) =>
    !topic || topicFor(fact) === topic;
  const checked = (result?.facts || []).filter(
    (fact) => matches(fact) && matchesTopic(fact),
  );
  const review = (result?.review_candidates || []).filter(
    (fact) => matches(fact) && matchesTopic(fact),
  );
  const issues = (result?.review_issues || []).filter(matches);
  const rejected = (result?.rejected_candidates || []).filter(matches);
  const issueEntries = [
    ...issues.map((item) => ({ kind: "issue" as const, item })),
    ...rejected.map((item) => ({ kind: "rejected" as const, item })),
  ];
  const currentLength =
    tab === "checked"
      ? checked.length
      : tab === "review"
        ? review.length
        : tab === "issues"
          ? issueEntries.length
          : history.length;
  const shownPage = Math.min(
    page,
    Math.max(0, Math.ceil(currentLength / 20) - 1),
  );
  const windowItems = <T,>(items: T[]) =>
    items.slice(shownPage * 20, shownPage * 20 + 20);
  return (
    <section className="source-panel facts-panel" aria-labelledby="facts-title">
      <h2 id="facts-title" className="sr-only">
        Reported facts for {document.filename}
      </h2>
      {configured === false && (
        <p className="source-warnings">
          OpenAI is not configured. Add OPENAI_API_KEY to the project’s ignored
          .env file and restart the API and worker.
        </p>
      )}
      {error && (
        <p className="batch-error" role="alert">
          {error}
        </p>
      )}
      {(state?.status === "not_requested" || state?.status === "failed") && (
        <p className="provider-note">
          Extracting sends this document’s source to OpenAI and may incur
          charges
          {plan ? ` · ${plan.segments} planned requests before retries` : ""}.
        </p>
      )}
      {state && (
        <div className="facts-status">
          <strong>
            {state.status === "not_requested"
              ? document.generation_error ? "Generation needs attention" : document.auto_generate ? "Generating…" : "Not requested"
              : state.status === "queued"
                ? "Generating…"
                : state.status === "processing"
                  ? "Generating…"
                  : state.status === "ready"
                    ? result?.review_candidates?.length
                      ? "Generated · review required"
                      : "Generated"
                    : "Generation failed"}
          </strong>
          {state.error && <p className="batch-error">{state.error}</p>}
          {document.generation_error && !state.error && <p className="batch-error">{document.generation_error}</p>}
          {!!state.segments?.length && (
            <span className="status-inline">
              {state.segments.filter((item) => item.status === "done").length}/
              {state.segments.length} segments complete ·{" "}
              {state.segments.filter((item) => item.status === "failed").length}{" "}
              failed
            </span>
          )}
          {(state.status === "failed" || (state.status === "not_requested" && (!document.auto_generate || document.generation_error))) && (
            <button
              className="primary-button"
              disabled={!configured || submitting}
              onClick={requestFacts}
            >
              {submitting
                ? "Requesting…"
                : state.status === "failed" || document.generation_error
                  ? "Retry generation"
                  : "Generate data"}
            </button>
          )}
          {Boolean(
            state.output?.proposed_result ||
            state.output?.segment_outputs?.some((item) => item.proposed_result),
          ) &&
            !pending && (
              <button
                className="source-button"
                disabled={submitting}
                onClick={recheck}
              >
                Recheck saved candidates locally
              </button>
            )}
          {pending && (
            <p className="batch-help">
              The worker will process this request. Source extraction status
              remains separate.
            </p>
          )}
        </div>
      )}
      {(result || !!state?.segments?.length) && (
        <details className="extraction-details">
          <summary>
            Extraction details{" "}
            {result?.warnings.length
              ? `· ${result.warnings.length} warnings`
              : ""}
          </summary>
          <p className="batch-help">
            Model results need review. Uploaded source is sent to OpenAI
            automatically after it is read; provider charges may apply.{" "}
            {plan ? `${plan.segments} requests planned before retries.` : ""}
          </p>
          {result && (
            <>
              <div className="facts-meta">
                <strong>{result.document_type}</strong>
                <span>Model coverage estimate: {result.coverage}</span>
                <span>
                  Organization: {result.organization || "Not identified"}
                </span>
                <span>
                  Provider:{" "}
                  {state?.output?.provider ||
                    state?.provider ||
                    "earlier provider"}
                </span>
                <span>Model: {state?.output?.model}</span>
              </div>
              <p className="batch-help">
                Coverage is a model estimate; relevant facts may be omitted.{" "}
                {result.coverage_note}
              </p>
              {result.warnings.length > 0 && (
                <ul className="source-warnings">
                  {result.warnings.map((warning, i) => (
                    <li key={i}>{warning}</li>
                  ))}
                </ul>
              )}
            </>
          )}
          {!!state?.segments?.length && (
            <>
              <p className="batch-help">
                Target records: {state.output?.completed_target_records ?? 0} /{" "}
                {state.output?.total_target_records ?? "—"}. Operational
                coverage: {state.output?.operational_coverage || "in progress"}.
              </p>
              <progress
                aria-label="Source segments completed"
                max={state.segments.length}
                value={
                  state.segments.filter((item) => item.status === "done").length
                }
              />
              <details>
                <summary>Segment status</summary>
                {state.segments.map((item) => (
                  <p className="batch-help" key={item.segment_id}>
                    {item.segment_id}: {item.status}
                    {item.error ? ` · ${item.error}` : ""}
                  </p>
                ))}
              </details>
            </>
          )}
        </details>
      )}
      {(result || history.length > 0) && (
        <div className="overview-switch" aria-label="Reported data view">
          <button
            aria-pressed={mode === "overview"}
            className={mode === "overview" ? "selected" : ""}
            onClick={() => setMode("overview")}
          >
            Overview
          </button>
          <button
            aria-pressed={mode === "details"}
            className={mode === "details" ? "selected" : ""}
            onClick={() => setMode("details")}
          >
            All details
          </button>
        </div>
      )}
      {mode === "overview" && result && state && (
        <DataOverview
          result={result}
          state={state}
          onEvidence={onEvidence}
          onDrill={(target, filter = "") => {
            setTab(target);
            setTopic(filter);
            setSearch("");
            setPage(0);
            setMode("details");
          }}
        />
      )}
      <div hidden={mode !== "details"}>
        {topic && (
          <div className="topic-filter">
            Topic: {topic}{" "}
            <button
              onClick={() => {
                setTopic("");
                setPage(0);
              }}
            >
              Clear filter ×
            </button>
          </div>
        )}
        {(result || history.length > 0) && (
          <div className="data-controls">
            <div
              className="data-tabs"
              role="group"
              aria-label="Reported data categories"
            >
              {(
                [
                  ["checked", `Checked (${result?.facts.length || 0})`],
                  [
                    "review",
                    `Needs review (${result?.review_candidates?.length || 0})`,
                  ],
                  [
                    "issues",
                    `Rejected & issues (${(result?.rejected_candidates?.length || 0) + (result?.review_issues?.length || 0)})`,
                  ],
                  ["history", `History (${history.length})`],
                ] as const
              ).map(([target, label]) => (
                <button
                  key={target}
                  aria-pressed={tab === target}
                  className={tab === target ? "selected" : ""}
                  onClick={() => {
                    setTab(target);
                    setPage(0);
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
            {tab !== "history" && (
              <label className="data-search">
                <Icon name="search" size={16} />
                <span className="sr-only">Search reported data</span>
                <input
                  type="search"
                  placeholder="Search this document"
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    setPage(0);
                  }}
                />
              </label>
            )}
          </div>
        )}
        {currentLength > 20 && (
          <div className="source-pagination top-pagination">
            <button
              className="source-button"
              disabled={shownPage === 0}
              onClick={() => setPage(shownPage - 1)}
            >
              Previous
            </button>
            <span>
              Showing {shownPage * 20 + 1}–
              {Math.min((shownPage + 1) * 20, currentLength)} of {currentLength}
            </span>
            <button
              className="source-button"
              disabled={(shownPage + 1) * 20 >= currentLength}
              onClick={() => setPage(shownPage + 1)}
            >
              Next
            </button>
          </div>
        )}
        {tab === "history" && history.length > 0 && (
          <details className="review-details" open>
            <summary>Previous extraction runs ({history.length})</summary>
            <p className="batch-help">
              Archived results and their source snapshots are preserved locally.
            </p>
            {windowItems(history).map((run) => (
              <details className="review-item" key={run.id}>
                <summary>
                  {new Date(run.archived_at * 1000).toLocaleString()} ·{" "}
                  {run.job.status} · {run.job.provider || "earlier provider"} ·{" "}
                  {run.job.model || "unknown model"} ·{" "}
                  {run.job.prompt_version || "earlier version"}
                </summary>
                <p className="batch-help">
                  {run.job.audit
                    ? `Local revalidation archive · ${run.job.audit.validator_version}`
                    : "Earlier extraction archive"}
                  . The original result and source snapshot remain saved
                  locally.
                </p>
              </details>
            ))}
          </details>
        )}
        {result && (
          <>
            {result.facts.length === 0 && !result.review_candidates?.length && (
              <p className="batch-help">
                No supported reported facts were found.
              </p>
            )}
            {tab === "issues" && issueEntries.length > 0 && (
              <details className="review-details" open>
                <summary>
                  Review issues and rejected candidates (
                  {(result.review_issues?.length || 0) +
                    (result.rejected_candidates?.length || 0)}
                  )
                </summary>
                <p className="batch-help">
                  The following proposals were cleared or rejected and are not
                  accepted facts.
                </p>
                {windowItems(issueEntries).map((entry, i) =>
                  entry.kind === "issue" ? (
                    <div className="review-item" key={`issue-${i}`}>
                      <strong>
                        {entry.item.fact_index
                          ? `Fact ${entry.item.fact_index}`
                          : "Document"}{" "}
                        · {entry.item.field}
                      </strong>
                      <p>{entry.item.reason}</p>
                      <pre>{JSON.stringify(entry.item.proposed, null, 2)}</pre>
                    </div>
                  ) : (
                    <div className="review-item" key={`rejected-${i}`}>
                      <strong>
                        Rejected candidate {entry.item.fact_index}
                      </strong>
                      <p>{entry.item.reason}</p>
                      <pre>{JSON.stringify(entry.item.candidate, null, 2)}</pre>
                    </div>
                  ),
                )}
              </details>
            )}
            {tab === "review" && review.length > 0 && (
              <>
                <div className="reported-review-intro"><Icon name="alert" size={16} /><p>These proposals need review and are excluded from accepted facts. Open their evidence to check the label and value relationship.</p></div>
                <div className="fact-list">
                  {windowItems(review).map((fact, i) => <ReportedDetailCard key={i} fact={fact} review kind={document.kind} onEvidence={onEvidence} />)}
                </div>
              </>
            )}
            {tab === "checked" && (
              <div className="fact-list">
                {windowItems(checked).map((fact, i) => <ReportedDetailCard key={i} fact={fact} kind={document.kind} onEvidence={onEvidence} />)}
              </div>
            )}
            {tab !== "history" && currentLength === 0 && (
              <p className="empty-category">
                No matching items in this category.
              </p>
            )}
          </>
        )}
        {tab === "history" && !history.length && (
          <p className="empty-category">No previous runs for this document.</p>
        )}
        {currentLength > 20 && (
          <div className="source-pagination">
            <button
              className="source-button"
              disabled={shownPage === 0}
              onClick={() => setPage(shownPage - 1)}
            >
              Previous
            </button>
            <span>
              Showing {shownPage * 20 + 1}–
              {Math.min((shownPage + 1) * 20, currentLength)} of {currentLength}
            </span>
            <button
              className="source-button"
              disabled={(shownPage + 1) * 20 >= currentLength}
              onClick={() => setPage(shownPage + 1)}
            >
              Next
            </button>
          </div>
        )}
      </div>
    </section>
  );
}

function App() {
  const [docs, setDocs] = useState<Document[]>([]);
  const [view, setView] = useState<WorkspaceView>("library");
  const [selectedId, setSelectedId] = useState("");
  const [sourceUnit, setSourceUnit] = useState(1);
  const [sourceFromData, setSourceFromData] = useState(false);
  const [sourceFromChat, setSourceFromChat] = useState(false);
  const [dataTab, setDataTab] = useState<DataTab>("checked");
  const [dataSearch, setDataSearch] = useState("");
  const [dataPage, setDataPage] = useState(0);
  const [dataMode, setDataMode] = useState<DataMode>("overview");
  const [dataTopic, setDataTopic] = useState("");
  const [connection, setConnection] = useState<Connection>("loading");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [batch, setBatch] = useState<Batch | null>(null);
  const uploadInFlight = useRef(false);
  const refresh = useCallback(async () => {
    try {
      const response = await fetch(`${api}/api/documents`);
      if (!response.ok) throw Error();
      const data = await response.json();
      setDocs(data.documents);
      setConnection("connected");
    } catch {
      setConnection("offline");
    }
  }, []);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [refresh]);
  const readyDocuments = docs.filter((document) => document.status === "ready");
  const selectedDocument =
    readyDocuments.find((document) => document.id === selectedId) ||
    (!selectedId ? readyDocuments[0] : null) ||
    null;
  function openDocument(document: Document, target: WorkspaceView, unit = 1) {
    if (selectedDocument?.id !== document.id) {
      setDataTab("checked");
      setDataSearch("");
      setDataPage(0);
      setDataMode("overview");
      setDataTopic("");
    }
    setSelectedId(document.id);
    setSourceUnit(unit);
    setSourceFromData(target === "source" && view === "data");
    setSourceFromChat(false);
    setView(target);
  }
  async function upload(files: FileList | File[]) {
    const selected = Array.from(files);
    if (!selected.length || uploadInFlight.current) return;
    uploadInFlight.current = true;
    setBusy(true);
    setNotice("");
    setBatch({
      count: selected.length,
      bytes: selected.reduce((sum, file) => sum + file.size, 0),
      stage: "uploading",
      progress: null,
      results: [],
    });
    try {
      const results = await uploadBatch(
        `${api}/api/documents`,
        selected,
        (progress) => {
          setBatch((previous) =>
            previous
              ? {
                  ...previous,
                  progress,
                  stage: progress === "confirming" ? "confirming" : "uploading",
                }
              : previous,
          );
        },
      );
      setBatch((previous) =>
        previous ? { ...previous, stage: "complete", results } : previous,
      );
    } catch (error) {
      setBatch((previous) =>
        previous
          ? {
              ...previous,
              stage: "error",
              error: error instanceof Error ? error.message : "Upload failed.",
            }
          : previous,
      );
    } finally {
      uploadInFlight.current = false;
      setBusy(false);
      void refresh();
    }
  }
  async function retry(id: string) {
    try {
      const response = await fetch(`${api}/api/documents/${id}/retry`, {
        method: "POST",
      });
      if (!response.ok) throw Error("Could not retry this document.");
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Retry failed.");
    }
  }
  return (
    <div className={`shell${view === "qa" ? " shell-chat" : ""}`}>
      <Sidebar
        count={docs.length}
        view={view}
        navigate={(target) => {
          setView(target);
          if (target === "source") { setSourceFromData(false); setSourceFromChat(false); }
        }}
      />
      <main>
        <div className={`content${view === "qa" ? " content-chat" : ""}`}>
          {connection === "offline" && (
            <div className="offline" role="alert">
              <Icon name="alert" size={18} /> Cannot connect to the API. Check
              that the backend is running.
            </div>
          )}
          <div className="chat-host" hidden={view !== "qa"}>
            <ChatWorkspace
              docs={docs}
              online={connection === "connected"}
              active={view === "qa"}
              onCitation={(id, unit) => {
                setSelectedId(id);
                setSourceUnit(unit);
                setSourceFromData(false);
                setSourceFromChat(true);
                setView("source");
              }}
            />
          </div>
          {view === "fy" ? (
            <FyWorkspace
              docs={docs}
              online={connection === "connected"}
              onOpenSource={(id) => {
                setSelectedId(id);
                setSourceUnit(1);
                setSourceFromData(false);
                setSourceFromChat(false);
                setView("source");
              }}
            />
          ) : view === "eval" ? (
            <EvalComparisonPanel />
          ) : view === "qa" ? null : view === "library" ? (
            <>
              <div className="page-heading">
                <div>
                  <div className="page-eyebrow">
                    <span /> DOCUMENT INTAKE
                  </div>
                  <h1>Document library</h1>
                  <p>
                    Upload and organize your sustainability reporting sources.
                  </p>
                </div>
                <div className="workspace-tag">
                  <Icon name="leaf" size={16} /> LOCAL WORKSPACE
                </div>
              </div>
              <Summary docs={docs} />
              <UploadPanel
                busy={busy}
                notice={notice}
                batch={batch}
                docs={docs}
                onUpload={upload}
              />
              <Library
                docs={docs}
                retry={retry}
                inspect={(document) => openDocument(document, "source")}
                openFacts={(document) => openDocument(document, "data")}
              />
            </>
          ) : (
            <>
              <div className="workspace-heading">
                <div>
                  <div className="page-eyebrow">
                    <span />{" "}
                    {view === "data" ? "EXTRACTION REVIEW" : "SOURCE CONTENT"}
                  </div>
                  <h1>
                    {view === "data" ? "Reported data" : "Source explorer"}
                  </h1>
                  <p>
                    {view === "data"
                      ? "Review proposed values and their evidence."
                      : "Inspect the original extracted text and cells."}
                  </p>
                </div>
                {selectedDocument && (
                  <label className="document-picker">
                    <span>Document</span>
                    <Select label="Document"
                      value={selectedDocument.id}
                      options={readyDocuments.map((document) => ({ value: document.id, label: document.filename }))}
                      onChange={(value) => {
                        setSelectedId(value);
                        setSourceUnit(1);
                        setDataTab("checked");
                        setDataSearch("");
                        setDataPage(0);
                        setDataMode("overview");
                        setDataTopic("");
                      }}
                    />
                  </label>
                )}
              </div>
              {view === "source" && sourceFromChat && <button className="back-data" onClick={() => setView("qa")}>← Back to conversation</button>}
              {view === "source" && sourceFromData && (
                <button className="back-data" onClick={() => setView("data")}>
                  ← Back to reported data
                </button>
              )}
              {!selectedDocument ? (
                <div className="workspace-empty">
                  <Icon name="file" size={26} />
                  <strong>
                    {connection === "loading"
                      ? "Loading documents…"
                      : selectedId
                        ? "Selected document unavailable"
                        : "No extracted documents yet"}
                  </strong>
                  <p>
                    {selectedId
                      ? "This source is missing or still processing. Return to your conversation or choose a ready document from the library."
                      : "Add a document in the library and wait for source processing to finish."}
                  </p>
                  <button
                    className="source-button"
                    onClick={() => setView("library")}
                  >
                    Go to document library
                  </button>
                </div>
              ) : view === "data" ? (
                <FactsPanel
                  key={selectedDocument.id}
                  document={selectedDocument}
                  tab={dataTab}
                  setTab={setDataTab}
                  search={dataSearch}
                  setSearch={setDataSearch}
                  page={dataPage}
                  setPage={setDataPage}
                  mode={dataMode}
                  setMode={setDataMode}
                  topic={dataTopic}
                  setTopic={setDataTopic}
                  onClose={() => setView("library")}
                  onEvidence={(unit) => {
                    setSelectedId(selectedDocument.id);
                    setSourceUnit(unit);
                    setSourceFromData(true);
                    setView("source");
                  }}
                />
              ) : (
                <SourceInspector
                  key={`${selectedDocument.id}-${sourceUnit}`}
                  document={selectedDocument}
                  initialUnit={sourceUnit}
                  onClose={() => setView(sourceFromChat ? "qa" : sourceFromData ? "data" : "library")}
                />
              )}
            </>
          )}
          <footer>
            <span>
              VERDANT <i /> DOCUMENT WORKSPACE
            </span>
            <span>Built for a clearer view of your documents.</span>
          </footer>
        </div>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
