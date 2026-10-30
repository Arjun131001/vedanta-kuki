# Milestone 1 verification

## QA numeric-format correction

- Full backend suite: 117 passed. No agent-initiated provider calls were made.
- The same frozen set of 117 exact source passages improved from 112 accepted / 5 falsely rejected to 117 accepted / 0 rejected. Existing unsupported-number, unit, qualifier, comparison, and citation controls remain tested.
- The reported failed conversation was repaired explicitly with a labeled source-excerpt overview and seven citations from its original two-document snapshot. The previous failure/projection remains in local audit history; the original evidence was unchanged. The original model response was never stored and was not reconstructed.
- Normal broad AI summaries remain enabled. Invalid claims no longer discard supported claims; new raw proposals and validation diagnostics are retained privately for offline replay. See [QA sessions](QA_SESSIONS.md).

## Document Q&A sessions

- Full backend suite: 94 passed, including synthetic mocked-provider QA through the durable worker, follow-up history, restart persistence, selected-document isolation, duplicate submission protection, and numerical/citation checks.
- Frontend production build and nine existing frontend tests passed. Manual browser checks confirmed the new sidebar section, file picker, multiple-file chips, suggestion drafting, and disabled empty submission. No real question was sent from the browser.
- Read-only retrieval found the expected water consumption, water amount, annual workbook value, and Adani consumption references in their selected-document bundles. These are retrieval checks, not answer-accuracy scores.
- No live OpenAI calls were made. Calculation/FY aggregation and the final source-verified QA evaluation remain unfinished. See [QA sessions](QA_SESSIONS.md).

## Visual reported-data overview

- Frontend production build and all nine frontend tests passed: five upload tests and four overview tests covering conservative highlights, unchanged values, generic consumption labels, and rejection of incompatible or ambiguous reading selections.
- Manual browser checks against saved backend results: water highlights displayed 2,321 Cubic Meters and the reported amount without inventing missing currency/period metadata. Workbook counts matched 14 checked / 297 review / 49 rejected; review issues remained separate. Its highlighted candidates retained Needs review badges.
- Dashboard cards opened the relevant detail category; topic bars applied a topic filter. Source links opened the cited page, and returning retained Overview. The policy's failed extraction remained visible with 2/3 completed segments and no invented highlights.
- Dashboard counts and chart proportions are calculated from stored result items, not accuracy scores or sustainability impact. Individual reading bars explicitly leave meter identity unestablished and calculate no difference. No backend changes or new model requests were made. Responsive styles are included; browser flow checks used the desktop viewport.

## Sidebar workspace navigation

- Frontend production build and five upload tests passed. No backend changes or model requests were made.
- Manual browser checks: left-sidebar access to Reported data, library-row access to a selected workbook, document switching, category tabs, 20-item pagination, and search worked against actual saved backend results.
- Opening workbook evidence from review items 21–40 selected the correct sheet in Source explorer. Back to reported data retained the workbook, Needs review tab, and second page. Search then filtered the results and reset the page.
- Results no longer appear beneath the upload/library view. Extraction diagnostics are collapsed, and pagination is available above and below long lists. Styling includes compact navigation on narrow screens; the manual flow above was verified in the desktop browser viewport.

## Offline OpenAI evidence recovery

- 72 backend tests, five frontend upload tests, and production build passed. No new LLM requests were made.
- Saved Adani responses changed from 6 checked / 0 review / 35 rejected to 9 checked / 11 review / 21 rejected. Recovered references remain exclusively in review; unsupported optional metadata no longer discards supported core evidence. Contact details are explicitly rejected as irrelevant.
- The unchanged twelve probes improved from 5 matched / 2 review / 3 missing / 2 incomplete to 5 matched / 4 review / 1 missing / 2 incomplete. Both Adani values now appear in review, with no probe category regressions.
- Raw proposal hashes are unchanged; prior projections and segment snapshots were archived with before/after hashes, and repeated validation was idempotent. See [Offline evidence recovery](OFFLINE_EVIDENCE_RECOVERY.md) for method, reproducible replay, and limitations.

## OpenAI migration

- After explicit approval, Adani-only verification completed four OpenAI segment requests with no retries. Job status was `ready`, operational coverage 4/4. Six proposals passed local evidence checks; 35 were rejected: 13 nonexistent references, eight unsupported source labels, six unsupported values, six invalid line spans, two out-of-target references. Some checked proposals were irrelevant contact details, so checked count is not an accuracy measure. Three prior runs remained archived.
- Repeating the fixed local extraction probes after this bill replacement gave 5 matched, 2 needing review, 3 missing, and 2 incomplete (previously 6/3/1/2). Both Adani probes became missing. The provider integration works, but this real-document extraction regressed and is not ready for reliable question answering. No other document was sent to OpenAI.

- Live synthetic verification after key setup: API, frontend, and frontend API proxy returned HTTP 200; configuration reported `gpt-4o-mini` with a key present. One request containing an invented Acme electricity sentence returned strict structured JSON with one evidence-supported fact, zero review candidates, and zero rejected candidates (964 total tokens). No supplied document was sent during this check. Backend 62 tests, frontend five tests, and production build passed again. The subsequent approved bill verification is described above.

- Active provider changed to OpenAI with default model `gpt-4o-mini`. Configuration uses ignored root `.env` entries `OPENAI_API_KEY` and `OPENAI_MODEL`.
- Chat Completions requests use strict JSON Schema and `store: false`; existing local evidence validation remains in place. Refusals, incomplete outputs, authentication errors, and insufficient quota produce explicit failures.
- Provider is included in job fingerprints and provenance. Legacy Gemini jobs cannot be dispatched through OpenAI; replacing a run archives its segment payloads and saved responses.
- All 62 backend tests passed using mocked provider responses. Before key setup, local API verification returned `configured: false`, `provider: openai`, `model: gpt-4o-mini`; six source documents and their Gemini jobs were retained. At that stage no live OpenAI extraction had been performed; subsequent verification results are recorded above.

Latest coverage/evidence milestone: 59 backend tests, five frontend upload tests, and production build passed. The approved 35-request batch and three-request policy retest are documented in [Coverage and reading order](COVERAGE_AND_READING_ORDER.md), including incomplete policy verification and remaining extraction gaps.

Verified locally on 28 October 2026.

- Backend: eight automated tests passed. Covers persisted catalogue and files, exact-byte deduplication, real PDF/XLSX validation, upload limits and partial batches, bounded retries, terminal failures, lease recovery, stale completion rejection, and concurrent job claims.
- Frontend: TypeScript check and Vite production build passed.
- Live HTTP: a synthetic workbook upload returned HTTP 202 and `queued`. Re-uploading the same bytes with a different filename returned `duplicate: true` and the same document.
- Restart: stopped the API process and started a fresh one against the same database. Started the separate worker. The original document reached `ready`, with one sheet and `metrics_extracted: false`.
- Browser: the dashboard displayed one total document, one ready document, and the synthetic workbook's backend result.

These are software reliability checks, not the assignment's ten source-verified question-answering evaluations. The six dataset documents were subsequently supplied and all passed local readability validation. Source-verified evaluations still require a later extraction/answering milestone.

The current live preview uses port 5174 because 5173 was occupied. Its API process uses `FRONTEND_ORIGIN=http://127.0.0.1:5174`. Normal setup defaults remain documented in the README.

GitHub publication is pending the user's GitHub connection. No AWS resources were provisioned.

## Supplied dataset and interface refinement

- Imported all six supplied files through `backend/import_demo.py` and the regular HTTP upload endpoint. All six reached `ready` through the separate validation worker.
- Repeated the import: all six returned their existing document IDs and `ready` states, without duplicate documents.
- Confirmed the redesigned dashboard displays actual backend totals and all six source filenames (plus the original synthetic smoke-test workbook).
- Verified filename search with `BESCOM`: exactly the matching source remained visible, with `Showing 1 of 7 documents`.
- Refined the interface with forest/emerald/slate styling, SVG icons, accessible search and status filters, connection feedback, and an explicit validation-only notice. Production build passed.

## Bulk upload progress

- Five upload transport tests passed: measurable/unknown progress, confirmation events, duplicate outcomes, HTTP errors, timeouts, network errors, and malformed responses. Frontend production build passed.
- Browser test selected the existing Adani PDF and annual workbook together. The result panel showed `0 added`, `2 already in library`, `0 failed`, with both existing validation statuses. Library remained at six documents.
- Transfer percentage uses actual browser upload events for the entire multipart request, including overhead. At transfer completion the UI waits for the server response before showing per-file outcomes. Intermediate percentages on fast local uploads may be too brief to observe; event handling is covered by the transport tests.

## Milestone 2: persistent source extraction

- 15 backend tests passed, including known PDF text, empty-page warnings, source persistence and cell pagination, formula-cache gaps, upgrade backfill, stale-worker fencing, and extraction limits. Five upload tests and the frontend production build also passed.
- Upgraded the three documents in the user's current library without deleting or re-uploading files. Compared IDs and SHA-256 hashes before and after: all preserved.
- Compared every persisted PDF page's text with a fresh pdfplumber read of the corresponding original. Compared all 557 nonempty workbook cell locations and values with a fresh openpyxl read. All matched.
- Restarted the final API and worker and repeated the source comparison successfully, confirming source persistence.
- Browser checks opened workbook source inspection, selected the Quarterly Summary sheet, and displayed the PDF inspector's image-only-page warning. Library marks warning-bearing results explicitly.
- Direct source scans of the other supplied files also completed. These are parser/source checks, not the assignment's question-answering evaluations. Semantic facts, FY totals, and AI answers remain future milestones. OCR is not installed; pages without embedded text remain explicitly flagged.

## Milestone 3: Gemini fact extraction

- Full backend suite: 30 tests passed. Provider calls in tests are mocked. Includes reference/quote/number checks, field-specific evidence failures, separate durable fact jobs, deduplication, source/schema fingerprinting, lease fencing, and missing-key handling.
- Frontend build and five upload transport tests passed. The fact panel exposes manual start, status, configuration guidance, evidence links, and warnings.
- Live key detection and model access succeeded without returning or logging credentials. The ignored root `.env` is not tracked.
- Gemini 3.8 Flash timed out on generation. A tiny Flash-Lite diagnostic succeeded in about two seconds; the configured default was changed explicitly to Gemini 3.5 Flash-Lite.
- Synthetic field isolation identified the larger provider schema as incompatible. Omitting its array-size constraint while keeping the local limit resolved the provider rejection. A synthetic structured fact subsequently passed local checks; it was not inserted into the real library.
- The explicitly approved one-attempt Adani bill test returned output but failed evidence validation. No AI facts from it were saved. Three source documents remain intact. Full dataset extraction quality, FY calculations, QA, and source-verified evaluations remain unfinished.

## Candidate-level extraction review fix

- Full backend suite: 41 tests passed; frontend production build passed.
- Replaced document-wide metadata rejection with candidate-level review. Unsupported values and locations remain rejected; unsupported optional metadata is cleared with explicit issues. Display labels are separated from exact source labels.
- One additional user-approved, single-attempt Adani request returned three candidates. All initially lacked valid label context; the response and frozen source are now retained in the ignored database.
- Local-only v4 revalidation recovered one unique exact same-page label reference. Its association with the value remains unconfirmed, so it appears exclusively in `review_candidates`, not accepted `facts`. Two candidates remain rejected. Result coverage is partial: zero accepted, one needing review, two rejected.
- Revalidation made no further provider requests. This fixes auditability and failure granularity; it does not establish accurate automatic bill extraction. Improving label/context citations and evaluating all six documents remains outstanding before QA or aggregation.

## Evidence-ID extraction experiment

- Added deterministic PDF-line and Excel-cell evidence IDs, exact server-side resolution, prior-run archival, and fixed extraction probes.
- Final backend suite: 47 passed. Frontend build and five upload tests passed.
- Completed the user-approved six-document batch with one attempt per document and no automatic retries. Saved 19 checked facts, 19 review candidates, and 8 rejected proposals. All coverage remains partial.
- Twelve source-checked probes: 5 matched, 2 needing review, 3 missing, 2 not completed. See `EXTRACTION_COMPARISON.md` for individual cases and limitations. These are not the final ten-case QA evaluations.
