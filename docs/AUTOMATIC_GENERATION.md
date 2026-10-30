# Upload and generate automatically

Every new PDF/XLSX upload records durable generation intent. The source worker
first validates and extracts the file. The worker then queues its OpenAI fact
segments automatically. A restart between source completion and queue creation
recovers that intent without another upload. Exact duplicate files reuse the
same document, jobs and results; completed generation is not repeated at startup.

The document API retains source `status` for source inspection and adds
`generation_status`: `generating`, `generated`, `failed` or `not_requested` for
legacy source-only documents. The library and summary use generation status,
so source readiness alone never shows Generated. All segments must finish for
Generated; partial results remain available while Generating. If some segments
fail permanently, the final job shows Needs attention with its provider error.
Generated means processing finished, not that every proposed fact is correct.

Missing keys, unreadable files, empty/OCR-only sources and size limits produce
visible failures rather than a success label or a perpetual spinner. Source
failures retry parsing; generation failures retry generation using stored source.
Opening pages and polling status do not create provider calls.

The user requested a local reset on 30 October 2026. All ten local application
tables were cleared, including documents, source, queues, fact histories and
Q&A sessions/turns. Six uploaded originals were removed. Schema and environment
configuration were preserved. Ignored trial/debug artifacts outside the database
and upload storage were not part of this reset.

The dashboard remains at http://127.0.0.1:5174 and currently proxies to the updated
API on port 8001. The old API's port-8000 process could not be inspected safely;
the launcher supports a remembered alternate port rather than stopping an
unidentified process. `scripts/start-local.ps1` reuses the configured port on
subsequent runs. The worker runs separately and uses the same database.

For an intentional future local reset, stop this workspace's API/worker and run
`python scripts/reset-local-data.py --confirm-reset`. It verifies upload paths,
clears every application table transactionally, checks row counts and foreign
keys, compacts SQLite and removes only files directly in the uploads directory.

Verification: 113 backend regression tests and two additional generation-retry
API tests passed with synthetic data and mocked providers. All 14 frontend tests,
TypeScript checks and the production build passed. Read-only checks through the
dashboard confirmed automatic generation enabled, no documents and no Q&A sessions.
No live test upload was retained; the application is empty for the user's test.
