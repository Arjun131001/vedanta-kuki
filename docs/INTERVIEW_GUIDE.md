# KuKi sustainability assistant: Milestone 1 interview guide

## What this milestone demonstrates

The application accepts PDF and XLSX documents, persists their metadata and files, and validates them through a separate worker. The dashboard shows durable progress and failures. Uploading identical content does not create another document or validation job.

**Ready means ready for extraction.** The worker checks file readability and reports page or sheet counts. It does not extract sustainability metrics, classify reports, determine fiscal years, or call an LLM.

The six assignment documents were supplied on 28 October 2026 and loaded into the local document library. All passed file-readability validation. Synthetic fixtures verify software behavior, but cannot establish extraction accuracy on the assignment dataset. No question-answering evaluation results are claimed. This milestone does not provision AWS resources.

## 1. Follow one upload through the application

Start with the user action: select or drop a PDF or XLSX file. React renders the interface; TypeScript describes the data received from the API; Vite runs and builds the frontend. The browser sends file bytes as multipart form data.

In `backend/app/main.py`, `POST /api/documents` checks the file type and size, streams the upload into a temporary file, and calculates its SHA-256 digest. Streaming avoids reading an entire large upload into application memory at once. The original filename is display metadata; it is not trusted as a storage path.

The API registers the file and a queued job. Its response confirms intake, not completed validation. A batch response has a result for each file, allowing the interface to explain partial success.

Talking point: “A successful upload means the system has accepted responsibility for the file. Processing has its own lifecycle, which the user can observe.”

## 2. Explain what survives a refresh

Browser state is temporary. SQLite and the upload directory hold the durable state. `backend/app/store.py` is the boundary around database operations, so route handlers and the worker use the same rules.

The `documents` table stores identity, original filename, size, hash, storage key, timestamps, visible status, errors, and validation results. The `jobs` table stores execution status, attempt count, next eligible execution time, and lease ownership.

`GET /api/documents` restores the dashboard after a refresh. `GET /api/documents/{id}` retrieves one document. The browser reports server state rather than inventing completion based on an animation or timer.

Both the API and worker must use the same `DATA_DIR`. Its default is relative to the process working directory, so start both from the backend directory or set the same absolute path explicitly. Reusing this directory is what preserves records across restarts.

Talking point: “The frontend is a view of persisted state. Reloading the page does not restart the work or erase its result.”

## 3. Separate accepting work from executing work

`backend/app/worker.py` is a separate process. It claims a job, runs `validate_file`, and records success or failure. The API can accept uploads while the worker is stopped, and those queued jobs remain available when the worker starts.

`backend/app/validation.py` uses pdfplumber for PDF readability checks and openpyxl for bounded workbook checks. These libraries are present now to validate files; metric extraction is future work.

The visible document states are:

| State | Meaning |
| --- | --- |
| `queued` | Waiting for a worker or a scheduled retry. |
| `processing` | A worker has claimed the job and is validating the file. |
| `ready` | Validation succeeded; the file is ready for later extraction. |
| `failed` | A permanent error occurred or the attempt limit was reached. |

Job completion is stored as `completed`, while the document becomes `ready`. Updates to the document and its job happen in the same database transaction so the two representations stay consistent.

Talking point: “An in-memory background task disappears when its process dies. A persisted job lets processing resume independently of the HTTP request.”

## 4. Explain retries and crash recovery

A job claim uses a short SQLite write transaction. `BEGIN IMMEDIATE` serializes competing claims before a worker chooses and updates a job. The transaction ends before file parsing begins; otherwise one slow file would hold the database write lock.

A claim includes an expiring lease and a fresh owner token. While validation runs, a heartbeat renews that lease. After an interrupted worker stops renewing it, a subsequent worker can reclaim the expired job. Claiming counts as an attempt, including an attempt interrupted by a crash.

Completion is conditional on the worker still owning an unexpired lease. This matters when an old worker resumes after another worker has reclaimed its job: the old result must not overwrite the new result.

Retryable failures return the job to `queued` with a future `available_at`. Persisting that timestamp means a restart does not forget the retry schedule. Backoff grows between attempts and is capped. Permanent validation failures stop immediately; exhausted attempts also become `failed`.

`POST /api/documents/{id}/retry` lets a user requeue a failed document. It starts a new attempt budget on the existing job; it does not create a new uploaded document. Retrying unchanged invalid bytes will not repair the file.

Talking point: “This is at-least-once execution with guarded, repeatable completion. I would not claim exactly-once execution: a crash can happen after doing work but before recording its result.”

## 5. Explain duplicate uploads

The SHA-256 digest identifies file content. A renamed copy has the same digest; a changed file has a different digest. The database enforces a unique digest, and registration uses a transaction so simultaneous duplicate submissions do not race into two records.

An existing file returns the original document identifier and its current status. The job table also enforces uniqueness on document, job kind, and processing version. Future processing versions can therefore be modeled explicitly rather than accidentally scheduling the same operation twice.

This deduplication is application-wide for the local milestone. A future multi-user product would need an explicit tenant and access-control model before deciding the scope of deduplication.

Talking point: “The filename tells us what to display. The content hash tells us whether we already have these bytes.”

## 6. Run a short demonstration

Use the repository README for dependency installation and frontend startup. Use a small valid PDF or XLSX you are allowed to upload. Do not present synthetic files as the six assignment documents.

1. **Start the API and frontend, leaving the worker stopped.** From the backend directory, run `python -m uvicorn app.main:app --reload`. Open the frontend and upload the sample. Explain the returned identifier and `queued` state.
2. **Refresh the page.** The same document remains visible because the interface reloads it from SQLite.
3. **Restart the API using the same data directory.** The queued record remains present. This demonstrates persistence independently of the worker.
4. **Start the worker in another terminal.** From the same backend directory, run `python -m app.worker`. The document advances to `ready` after validation. For a small file, `processing` may be too brief to see; do not promise a visible delay.
5. **Inspect the result.** Explain the page or sheet count and the explicit `metrics_extracted: false` validation field. No extracted sustainability values should be shown.
6. **Upload identical bytes under another filename.** The response identifies a duplicate and reuses the original document. The document count should not increase.
7. **Demonstrate an invalid file.** A small text file renamed to `.xlsx` can pass the extension check but fail the worker's structural check. Explain why filename validation alone is insufficient.
8. **Run the backend tests.** From the backend directory, run `python -m pytest -q`. Report the actual result observed in that run.

For crash recovery, prefer the deterministic lease-recovery test in `backend/tests/test_intake.py`: it claims a job, advances the claim clock past expiry, reclaims it, and verifies that the stale worker cannot finish. This avoids relying on precisely timed manual termination during a very short validation task. Explain the test as a simulation of recovery; do not describe it as a live process-kill test.

## 7. Discuss the tradeoffs candidly

- **SQLite keeps the local milestone understandable.** WAL improves reader/writer coexistence, but SQLite still serializes writers. A larger multi-instance deployment would need a fresh database and queue design.
- **A database transaction does not include the filesystem.** The file move and database commit cannot be one atomic operation. Normal exceptions can be cleaned up, but a hard crash can leave unreferenced files; reconciliation and retention are deployment work.
- **A heartbeat protects ownership, not resource usage.** Parser time limits and stronger process isolation would be needed for an untrusted production upload service.
- **Validation has a deliberately narrow meaning.** Readability and structural checks do not prove that a report contains relevant data or that every spreadsheet cell is semantically correct.
- **The current retry row is operational state, not an immutable audit log.** Future audit requirements would justify separate attempt and processing-result records.

## 8. Connect this foundation to the remaining assignment

Build the next milestones in this order:

1. Continue inspecting the six supplied source documents. File hashes and formats are recorded; identify company and reporting period with evidence before calculating any totals.
2. Extract deterministic source material with pdfplumber and openpyxl. Preserve PDF page references and spreadsheet sheet/cell coordinates alongside values and units. Identify scanned pages that need a separate OCR decision.
3. Add classification and structured metric extraction. Keep reported values, normalized values, fiscal years, boundaries, and evidence distinguishable. Represent unavailable information explicitly.
4. Add evidence-backed QA. Answers should point to the supporting source location and avoid treating missing evidence as a zero value.
5. Evaluate against labeled expectations from the supplied documents. Measure classification, value/unit/year extraction, evidence correctness, and unsupported-answer behavior separately. Publish results only after running the evaluation.

Every future classification, extraction, and QA **system prompt** must contain this exact assignment-required sentence:

> You are Harvey Specter, acting as a meticulous sustainability data analyst.

There are no such LLM calls in Milestone 1. The sentence is a future prompt requirement, not evidence that any extraction or QA capability is already implemented.

Deployment planning can follow once the local workflow and evaluation are established. No AWS account, service, or billable resource needs to be provisioned to demonstrate this milestone.
