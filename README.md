# Verdant document workspace · source extraction

For the AWS deployment implementation targeting `vedant-a.duckdns.org`, see [deployment setup](deploy/README.md). DuckDNS registration is complete; AWS provisioning and DNS configuration are still required.

A local workspace for uploading PDF and XLSX reports. A background worker reads each file, then automatically generates reported data with OpenAI. Documents show **Generating** until generation completes and **Generated** afterwards. Generated results still require evidence review. Configure `OPENAI_API_KEY` in the ignored project-root `.env`; provider charges may apply. Missing configuration or failed jobs show **Needs attention** with a retry action.

## Set up on Windows

Install Python 3.11 or newer and Node.js 20 or newer (and pnpm). Open PowerShell in this folder. Use three terminals so each process stays running.

1. Create a virtual environment and install the backend dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
   ```

2. Start the API in the first terminal. It creates the SQLite database and upload directory on first run.

   ```powershell
   cd backend
   ..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
   ```

3. Start the worker in a second terminal. It consumes jobs independently, so closing the API does not erase the queue.

   ```powershell
   cd backend
   ..\.venv\Scripts\python.exe -m app.worker
   ```

4. Start the dashboard in a third terminal:

   ```powershell
   cd frontend
   pnpm install --frozen-lockfile
   pnpm run dev
   ```

   Open the address printed by Vite (normally http://localhost:5173). Add up to 10 PDF or XLSX files at once, then watch their status change. Stop each process with Ctrl+C. To restart, repeat steps 2–4; the database and files remain in `backend/data`.

## Load the demo dataset

The six KuKi source files are kept outside Git. With the API and worker running, load your local dataset using the normal upload API:

```powershell
cd backend
..\.venv\Scripts\python.exe import_demo.py "C:\path\to\kuki-assignment-dataset"
```

Repeated imports reuse existing documents by content hash. The library reflects the files actually uploaded to this local database. No sustainability totals are calculated yet.

## How it works

The API streams each file to a temporary file, enforces a 25 MB per-file limit, computes its SHA-256 hash, and records one document and validation job per unique content hash. A duplicate upload returns the existing document. Files use generated storage names; the original name is only display metadata. Each batch reports individual successes and errors.

SQLite stores the document and job state. The worker claims one job in a short transaction, then validates and extracts source content outside that transaction. A renewable lease and random token prevent an old worker from overwriting a newer claim. Interrupted jobs return to the queue when their lease expires; transient errors retry with bounded exponential backoff. A failed document can be manually requeued in the dashboard. The worker uses pdfplumber for page text and openpyxl for cell coordinates, values, types, formats, formulas, and available cached values. It atomically stores versioned sources only if it still holds the lease. Open a ready document’s source inspector to navigate pages or sheets; cells are paginated. Neither parser infers report metrics. Existing ready documents without sources are requeued once when the service starts.

The API provides `GET /api/health`, `GET /api/documents`, `GET /api/documents/{id}`, `POST /api/documents` (multipart field `files`), and `POST /api/documents/{id}/retry`, and `GET /api/documents/{id}/sources` (optional `unit`, `offset`, and `limit`). Interactive documentation is available at http://localhost:8000/docs.

## Configuration and tests

Defaults work without an environment file. See `.env.example` for optional variables; set them in each terminal before starting its process. The API and worker must use the same `DATA_DIR`.

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest
```

`frontend`: `pnpm run build` checks TypeScript and creates a production bundle. For development, the API allows the default Vite origin only. Change `FRONTEND_ORIGIN` if needed.

## Current limits

This is a local, single-user milestone, with no login, deletion, semantic metric extraction, OCR, or cloud deployment. Data is stored unencrypted on disk; do not use sensitive documents on an untrusted machine. SQLite is suitable for this local workload, not multi-host deployments. Source extraction does not establish semantic correctness or safety. Image-only PDF pages are retained as empty pages with an OCR warning; the supplied BESCOM report includes an image-only second page. Formulas are not recalculated and cached values can be missing or stale. Source limits are 10 million text characters, 100,000 nonempty workbook cells, 100,000 rows, 256 columns, and 2 million scanned cell positions; a limit breach fails the job instead of silently truncating it. XLSX archives are limited to 100 MB expanded and 10,000 entries; PDFs are limited to 2,000 pages. A machine crash between moving a file and committing its database row may leave an unreferenced file; it will not be exposed in the library. Uploads and the database are ignored by Git.


### Start the workspace in the background

After completing the installation above, run `powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1` from the project folder. Open http://127.0.0.1:5174. The launcher starts the API, worker, and frontend as separate local processes and writes their logs to `tmp/`. These processes must keep running for the dashboard and validation to work. Running the launcher again checks for an existing API and worker; it does not stop services using the required ports.

During development, Vite proxies same-origin `/api` requests to the local API. The launcher remembers its target in the ignored `frontend/.env.local`. Use `scripts/start-local.ps1 -ApiPort 8001` if the default port 8000 is occupied; the dashboard remains at port 5174. `VITE_API_PROXY_TARGET` controls the development proxy. Set `VITE_API_URL` only for a different browser API origin. A production web server must route `/api` to the backend or provide that override at build time.

During a batch upload, the progress bar reports bytes transferred for the whole multipart request (including request overhead). Once sent, the dashboard waits for the server's per-file results; document validation continues independently in the library.

## Ask your documents

The **Ask your documents** sidebar section provides saved, document-scoped Q&A conversations. Select extracted files, ask a question, and open numbered citations to inspect the supporting page or sheet. Lookup questions run through the persistent Python worker and OpenAI; selecting files or opening history does not call the model. Explicit calculation and Indian financial-year total questions are answered by a local deterministic calculator (no model call) and label results as system-calculated. The selected files stay fixed within a conversation; start a new chat to change them. See [QA sessions](docs/QA_SESSIONS.md) and [eval comparison](docs/eval/COMPARISON.md).

**Financial year** builds coverage and calculated totals for a selected FY (1 Apr–31 Mar) over chosen documents via `POST /api/fy/summary`. **Evaluation** shows committed baseline vs improved scorecards from `docs/eval/`.

## Automatic OpenAI reported facts

Use the left navigation to switch between **Document library**, **Reported data**, and **Source explorer**. Data and source views share the selected document, so inspecting a value no longer appends panels beneath the upload area. Viewing stored results or source evidence does not start model extraction.

**Reported data → Overview** presents source-linked value cards, result-distribution charts, approximate topic counts, and segment progress from saved backend results. Counts are calculated by the dashboard; highlighted values retain their reported value, unit, organisation, period, and review status. Click a summary card or topic to open filtered details. Independent reading bars appear only for a unique previous/current selection with matching explicit unit and organisation; they do not establish shared meter identity or calculate consumption changes. Unknown metadata remains unknown, and the dashboard does not sum sustainability values or invent trends. **All details** retains the searchable, paginated evidence and audit views.

Saved OpenAI responses can be rechecked without another model request. Conservative exact-reference recovery remains explicitly marked for review, with original and corrected IDs visible in the dashboard. Revalidation preserves the previous projection and immutable model proposals. See [offline evidence recovery](docs/OFFLINE_EVIDENCE_RECOVERY.md) for the read-only replay command, comparison, and safeguards.

The source inspector is local. For automatic document classification and reported facts, create the ignored project-root `.env` file with `OPENAI_API_KEY=...` and optionally `OPENAI_MODEL=gpt-4o-mini`, then restart both API and worker. Obtain a key through the OpenAI platform; keep it out of Git, chat, and screenshots. Environment variables take precedence over `.env`. The dashboard shows whether a key is configured, never the key itself.

Upload a document to begin generation automatically. Reading source and generating data run in the durable background worker; no **Extract facts** click is required. Pending uploads resume after restart. Opening results or restarting does not re-extract completed documents. Duplicate uploads reuse their existing job/result. Failed generation can be retried from the library or data panel; temporary provider failures have bounded retries. Previous results remain in history. The provider read timeout is 300 seconds. Source, model, prompt and schema fingerprints identify requests. Existing legacy documents are not automatically sent to a provider merely because the app was upgraded.

The model proposes classifications and facts. The service checks cited page text or spreadsheet cell values and checks numeric values and reported context against cited quotes before storing results. Each proposed fact needs a verbatim source label, a supported value and valid source location. Unsupported core claims are rejected individually; unsupported organization, unit, period, or currency is cleared and shown as a review issue. Display labels are AI-proposed and require review. The current pipeline resolves evidence from indexed source references. The earlier quote-based validator could place a uniquely located same-page label in a separate needs-review category; that legacy behavior applies only to its archived results. Units are checked case-sensitively against individual cited quotes. These checks do not prove a value's interpretation or organization attribution is correct; review the source references. Blank pages, stale or missing formula caches, conflicts, and unknown organizations remain visible as warnings. No unit conversions, totals, fiscal-year calculations, or question-answering are performed. Each segment is limited to 60 sustainability-relevant facts and records a model coverage estimate; relevant facts may still be omitted. Source gaps or a reached cap mark coverage partial. A segment exceeding 80,000 serialized characters is rejected before any provider call rather than silently truncated. PDF evidence spans may contain up to eight ordered, contiguous lines on one page. API endpoints are `GET /api/facts/config`, `GET /api/documents/{id}/facts`, and `POST /api/documents/{id}/facts`. The original structured proposals and source snapshot are stored locally for audit. The **Recheck saved candidates locally** action applies the current validator to that snapshot without an API key or provider call; output records the validator version separately from the model, prompt, and schema. Earlier failed requests that did not save proposals cannot be reconstructed. Tests use mocked HTTP and do not contact OpenAI.

The current extraction request uses a versioned index: nonempty PDF lines and nonempty spreadsheet cells receive deterministic reference IDs. The model returns reference IDs; the server resolves them to source text and validates the proposed values and metadata. Associations across lines or cells are model-proposed and appear as needs-review candidates, not automatically checked facts. When the label and value are on the same indexed line or cell and pass evidence checks, they appear as checked facts; all model results still require human review. The full source snapshot and previous output are archived locally before a later request replaces them; `GET /api/documents/{id}/facts/history` retrieves prior runs. Earlier quote-based candidates remain archived, but the current indexed validator does not revalidate their older format. Re-extraction is always manual, and source/index size limits reject oversized requests instead of silently truncating them.

Fact extraction is segmented. The plan displayed before requesting facts shows the number of provider calls before retries. PDF pages are processed in bounded line groups with neighboring context; workbook sheets are processed in four-row groups with sheet title and header context. Every nonempty source record is a target once; context is not counted again. Completed segments and their proposals persist locally, and a retry resumes failed segments without calling completed ones. Operational coverage means target segments finished, not that the model found every relevant fact. Source gaps and per-segment model estimates remain separate warnings. The plan is also available at `GET /api/documents/{id}/facts/plan` without a provider call.

PDF source extraction preserves the original page text and, when a conservative gutter detector identifies a narrative two-column layout, also stores separate reading blocks with page coordinates. The source inspector displays both. Evidence spans cannot cross reading blocks. Existing PDF sources created before this layout version are queued once for local reprocessing on restart, unless a fact job for that document is active; earlier fact snapshots and outputs remain preserved. The detector may miss unusual layouts, and column interpretation remains subject to review.

Spreadsheet index records distinguish literal values, cached formula values, and formulas with no cache. Rechecking saved segment results locally can add unproposed numeric cells under an exact unit-bearing column header as **locally mapped cells needing review**. Their row/header associations are not verified facts, their original stored values are not recalculated, and an explicitly proposed or rejected value is not revived. Rechecking does not call the provider.
