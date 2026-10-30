# Milestone 2: inspectable source content

This milestone adds deterministic source extraction to the document library. PDF pages expose embedded text, and workbooks expose nonempty cells with sheet names and cell coordinates. The content is persisted so it can be inspected after an API or worker restart.

This is source preparation, not sustainability metric extraction. There are no LLM calls, no selected LLM provider, no inferred fiscal years, no emissions calculations, and no AI-generated answers. The six supplied documents can exercise this workflow, but successful processing does not establish the correctness of future metric extraction.

## 1. Distinguish three different questions

| Question | What answers it |
| --- | --- |
| Can a parser open the file? | Readability validation from Milestone 1. |
| What text and cells are stored in it? | Deterministic source extraction in this milestone. |
| Which figures answer a sustainability question? | A future interpretation and evidence-grounded QA stage. |

A workbook can open successfully while containing formulas with no saved results. A PDF can open successfully while containing scanned images with no embedded text. Neither situation should be represented as proof that the document contains no sustainability information.

## 2. Extend the existing worker pipeline

The API still accepts uploads and persists a job. The worker now performs two operations in sequence:

```text
Upload accepted → Queued → Validate file → Extract source content → Persist result
```

`backend/app/worker.py` calls `validate_file`, followed by `extract_source` in `backend/app/extraction.py`. This remains one durable job with one lease and retry budget. A retry reruns both steps; it does not resume halfway through a page or worksheet.

The existing database job identifier remains kind `validation`, version `1` for compatibility. It now represents the combined validation and source-extraction pipeline. Source results have their own version field. A future change to extraction semantics should introduce an explicit new result version and upgrade policy rather than silently treating older results as equivalent.

Document statuses remain `queued`, `processing`, `ready`, and `failed`. In Milestone 2, `ready` means the worker stored the source result successfully. It does not guarantee that every page has text or that source content is complete enough for analysis. The interface must show warnings alongside the result. The library's processing label covers validation and extraction; a timer or upload percentage cannot measure this work.

Talking point: “I expanded one reliable pipeline before introducing independent processing stages. The tradeoff is that a failed extraction repeats validation on retry.”

## 3. Preserve source locations

For a PDF, each source unit records its original one-based page number and extracted text. The application can refer to the original document identifier, extraction version, and page number when displaying or citing source content.

For a workbook, each source unit records a worksheet name. A cell record preserves its original coordinate, source type, value, formula where applicable, and cached formula value. Sheet names and coordinates are evidence locations; they must not be replaced by the row number in the paginated preview.

These are coarse source references. PDF text does not yet have word bounding boxes, reconstructed tables, or chart interpretation. Workbook values do not reproduce every visual formatting choice in Excel. Future metric records must retain their own links to these source locations.

Talking point: “An extracted number alone is difficult to audit. Keeping its page or sheet and cell gives a reviewer a way back to the evidence.”

## 4. Treat formulas and cached values separately

The extractor opens a workbook twice in read-only mode:

- `data_only=False` exposes formulas and ordinary cell values.
- `data_only=True` exposes saved formula results when the workbook contains them.

For example, `C8` may contain `=SUM(C2:C7)` and a saved result of `125`. The source record preserves both. The application does not calculate `125` itself and cannot guarantee that the saved result is up to date.

When a formula has no available cached result, its formula remains visible and its cached value is unavailable. That is not a zero. A warning explains that the formulas were not recalculated. Recalculation by a spreadsheet engine would be a separate capability.

Dates and times are serialized in an interoperable string representation. Cell source types help distinguish text, numbers, formulas, and other stored values. This is still source representation, not unit normalization or metric interpretation.

## 5. Make missing text and limits visible

PDF extraction uses embedded text through pdfplumber. A page with no extracted text produces a warning that OCR may be needed. The page may be scanned, image-based, or genuinely blank; absence of embedded text alone does not decide which explanation is correct. An entirely image-based PDF can therefore have a stored source result consisting of page records and warnings, without usable extracted text. It must not be presented as a fully readable report.

There is no OCR stage in this milestone. Mixed PDFs may have useful text on some pages and warnings on others. Review the warnings before relying on a source preview.

Extraction has explicit bounds to avoid unbounded source output and worksheet scans:

| Bound | Current limit |
| --- | --- |
| PDF extracted text | 10,000,000 characters per document |
| Nonempty workbook cells | 100,000 across the workbook |
| Worksheet extent | 100,000 rows and 256 columns |
| Workbook cell positions to scan | 2,000,000 across worksheets |
| API cell preview page | Default 100, maximum 200 cells |

The extraction limits fail explicitly instead of silently omitting the remainder of a document. An inflated worksheet extent caused by formatting can hit a limit even when relatively few cells contain values. These bounds are not a complete parser sandbox or a guaranteed CPU-time limit.

## 6. Persist results without losing existing uploads

`backend/app/store.py` adds two tables while keeping existing document records, files, and job identities:

- `source_results` stores the document identifier, extraction version, format, and summary, including warnings.
- `source_units` stores ordered page or worksheet units and their content, keyed by document, version, and unit index.

On startup, an existing `ready` document without a version 1 source result is requeued for the expanded pipeline. This resets its attempt budget and preserves its uploaded file and existing validation metadata during requeueing. Repeated startup does not create another document or job. Failed legacy documents still require the normal retry action.

Stop an older worker before starting the upgraded worker. An old worker knows only about validation and can otherwise mark work ready without producing source content.

The worker parses outside the database write transaction. At completion, the store checks that the worker still holds a valid lease, then writes the summary and source units and completes the job in the same transaction. If the transaction fails, it rolls back. A stale worker cannot replace source content after another worker has taken ownership.

The current version is a replaceable snapshot for each document and extraction version, not an immutable record of every attempt. Separate run history and reproducible processor fingerprints can be added when audit requirements justify them.

Talking point: “The upgrade reuses stored files, and completion is atomic with the source snapshot. A document cannot become ready from this worker while only half its source units have committed.”

## 7. Inspect the persisted content

The source endpoint is:

```text
GET /api/documents/{document_id}/sources
GET /api/documents/{document_id}/sources?unit=1
GET /api/documents/{document_id}/sources?unit=1&offset=100&limit=100
```

The first form returns the summary and page or worksheet choices. Selecting a unit returns its content. Workbook cell previews are paginated; offsets select entries in the stored nonempty-cell list, not worksheet row numbers. Original coordinates remain attached to each entry.

The endpoint returns a missing-document error for an unknown document and a not-yet-complete response when source extraction has not produced a result. Reading a preview reads persisted content; it does not rerun extraction.

The frontend should let a user select a document, inspect warnings, choose a page or worksheet, and navigate the available content. Text should be rendered as text, and workbook formula strings should remain inert content.

## 8. Demonstrate the milestone

1. Start the upgraded API and worker using the same existing data directory. Previously validated documents without sources will requeue automatically.
2. Open a processed PDF and select two different pages. Compare their page numbers and text against the original file.
3. Open a workbook and select a worksheet. Compare a few visible coordinates and values against the original workbook. Navigate beyond the first preview page when enough nonempty cells exist.
4. Inspect a formula cell if the source workbook contains one. Explain the distinction between its formula and saved result. Use a clearly labeled synthetic fixture if the supplied files do not contain a suitable example.
5. Demonstrate an empty-text PDF page or a synthetic image-only fixture and show its warning. Do not describe this as completed OCR.
6. Restart the API and reload a source preview. It should read the existing persisted result.
7. Re-upload identical bytes. Deduplication should reuse the same document instead of duplicating the source library.
8. Run the relevant tests and report their observed outcome. Functional source checks are not a sustainability extraction accuracy score.

Useful checks include migration of an old ready record, preservation of page and cell locations, formula-cache warnings, explicit size-limit failures, preview pagination, persistence across restarts, and rejection of a stale worker's source writes.

## 9. Prepare for evidence-grounded AI later

A future AI stage can consume bounded source passages and cells with stable document and location references. It should output structured claims linked to those references, distinguish reporting years and units, and state when evidence is missing. Source documents are data, including any instructions embedded in their text.

Every future classification, extraction, and QA system prompt must include the assignment-required sentence exactly:

> You are Harvey Specter, acting as a meticulous sustainability data analyst.

No system prompt is executed in this milestone. Provider selection, metric schemas, evidence-grounded question answering, and labeled evaluation are subsequent decisions. No AWS resources are provisioned for this step.
