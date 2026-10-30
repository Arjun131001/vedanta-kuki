# Milestone 3: classification and reported facts with Gemini

This milestone adds a manually requested AI step after deterministic source extraction. Gemini classifies a document and proposes facts explicitly reported in its stored page text or worksheet cells. The application checks the structured response and its source references before saving a result.

**Evidence checks are not semantic verification.** A quote can exist in the source while a model associates it with the wrong metric, entity, or reporting context. Results need review against the linked evidence. This milestone does not add question answering, fiscal-year aggregation, unit conversion, calculated emissions, or accuracy scores for the six-document dataset.

## 1. Configure the provider without exposing the key

Create or edit `.env` at the repository root, alongside `README.md`:

```dotenv
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-3.5-flash-lite
```

Replace the placeholder locally. Do not put the key into frontend code, browser storage, screenshots, test fixtures, or a public commit. The repository ignores `.env`; `.env.example` contains placeholders only. Existing process environment values take precedence over values loaded from this file.

Restart the API and worker after changing configuration. The frontend configuration endpoint exposes whether a key is present and which model is configured; it does not return the key. A present key is not proof that it is valid or that the account has quota.

Without `GEMINI_API_KEY`, a fact request returns configuration guidance and no provider request is made. Local uploads, validation, and source inspection remain useful without the key. Do not present mocked responses or source previews as successful live Gemini extraction.

## 2. Understand the free-tier boundary

As checked on October 29, 2026, Google's pricing page lists free-tier input and output for the standard Gemini 3.5 Flash-Lite API. Availability still depends on the project, model access, and quota; setting a model name in this application does not enforce free billing. The application does not enable billing or switch providers automatically. [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)

The initial 3.8 Flash configuration timed out on generation requests, including a tiny diagnostic prompt. A developer-run 3.5 Flash-Lite diagnostic completed in about two seconds, so the local default was changed explicitly. This is observed availability for this account and run, not an accuracy comparison or a promise of future latency.

The free tier has request and token limits. Limits apply at project level, and the active allowance should be checked in Google AI Studio. A rate-limit response is not evidence that extraction succeeded. [Gemini API rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)

Google's pricing page distinguishes data use by tier: free-tier content may be used to improve its products, while the listed paid-tier policy differs. Clicking Extract facts sends stored source text and cells to Google, including any sensitive information contained in them. This is separate from uploading a file into the local library. [Gemini API pricing and data-use notes](https://ai.google.dev/gemini-api/docs/pricing)

## 3. Keep local processing and AI work separate

The source pipeline still produces persisted PDF page text and worksheet cells. Fact extraction has a separate durable queue, so a provider failure does not turn a readable source document into a failed upload and does not require parsing the file again.

```text
Local upload → Source extraction → Source preview
                                      |
                              User selects Extract facts
                                      |
                         Fact queue → Gemini → Local checks
                                      |
                              Saved facts or an error
```

The current worker process services both kinds of work, but they have independent queue records and completion paths. Merely uploading a file, restarting the services, or opening its preview must not initiate a new AI request. Previously requested queued work can resume after a restart.

The API exposes:

```text
GET  /api/facts/config
POST /api/documents/{document_id}/facts
GET  /api/documents/{document_id}/facts
```

The POST requires source content to be ready. Reading the GET endpoint returns status and saved output rather than requesting another generation. Fact states are `not_requested`, `queued`, `processing`, `ready`, and `failed`, separate from the source document's status.

## 4. Make structured output useful without overstating it

`backend/app/facts.py` defines the response models and system instruction. The request uses Gemini's JSON schema response format through `generateContent`. Structured output controls response shape; application checks are still needed for the values. [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)

The result contains a document classification, organization attribution when supported, reported facts, and warnings. A fact preserves its label, reported value as text, unit, reported period, currency when relevant, and its source evidence. Local numeric-token checks use decimal arithmetic when comparing plain numbers; this does not create a normalized numeric metric model. Unknown metadata should remain unavailable rather than being guessed. The source type determines whether evidence points to a PDF page or a worksheet and cell coordinates.

A reported fiscal-year label is source text, not permission to invent its start and end dates. A saved spreadsheet formula result is not a value calculated by this application. Missing formula caches and pages without embedded text remain limitations of the available evidence; calling an LLM does not supply OCR or recalculate a workbook.

The system instruction includes the assignment-required sentence exactly:

> You are Harvey Specter, acting as a meticulous sustainability data analyst.

It also treats instructions embedded inside documents as untrusted source content and prohibits derived values. Any later separate classification, extraction, or QA system prompt must retain the required sentence.

## 5. Explain what evidence checks establish

The application checks source-unit existence, quotation presence with whitespace normalization, spreadsheet coordinate validity, reported-value support, and supported metadata or organization references. It rejects invalid structured responses instead of quietly displaying them as completed facts.

These checks can catch a nonexistent page, fabricated quote, wrong cell address, or a number absent from the cited evidence. They do not prove that a nearby unit belongs to that number, that a named company is the reporting entity, or that a classification is correct. Review the metric label and its surrounding context as well as the quote.

Spreadsheet metadata often lives in separate cells: a value in `C8`, a unit in `C2`, and a period in `D1`. Each supporting cell needs an honest reference. Do not invent a continuous source quote by joining separate cells, and do not treat a match in one cited cell as proof of every other cited cell's meaning.

Use “AI-extracted facts; review evidence” in the interface. Avoid labels such as “verified,” “audited,” or “100% accurate.” An empty fact list means the request returned no supported facts under the current process, not proof that the original document contains none.

## 6. Deduplicate requests and preserve their context

Repeated clicks reuse an active job, and a completed result is reused when its request fingerprint matches. The current fingerprint covers the serialized source snapshot, including source version, the configured model, and the prompt version. Prompt/schema revisions must invalidate that identity; the current version token must be incremented when either contract changes unless a separate schema hash is added. A filename or document identifier alone does not establish that two generations used the same inputs and instructions.

The worker uses the persisted source snapshot for that request, and saved output records its source hash. The current queue holds one result per document. A manually requested replacement can replace that record; it is not an immutable history of every extraction run. See `backend/app/fact_queue.py` for the persisted fingerprint and snapshot. A future audit-history feature would preserve superseded runs separately.

Deduplication is local application behavior, not a guarantee of exactly-once execution at the provider. A request can finish remotely just before the worker crashes or loses its connection. Retrying may consume more quota and, on a paid project, may incur another charge. The application cannot infer remote billing outcome from a timeout.

## 7. Recover failures without mixing up statuses

Fact jobs persist attempt counts, next eligible retry times, and expiring leases. A heartbeat renews ownership while the request is running. Completion checks the lease before saving output, preventing an expired worker from overwriting a newer result.

Temporary network failures, rate limits, and provider service failures have a bounded retry budget. Authentication and invalid-request failures need configuration changes. Incomplete, blocked, or locally invalid output must not be treated as a successful empty result.

The current single-request path caps serialized source content at 300,000 characters. It rejects larger inputs instead of silently selecting the first pages and claiming complete extraction. This is an application bound, not the model's token limit. Multi-request chunking and explicit coverage tracking are future work.

The focused prompt requests at most 60 core sustainability facts and a coverage estimate. The local validator enforces this cap; the provider schema omits `maxItems` because the fully constrained schema returned `400 INVALID_ARGUMENT` in a live synthetic test. Source gaps or reaching the cap produce partial-coverage warnings. Model-estimated complete coverage still requires review. Connection timeout is 15 seconds and read timeout is 300 seconds, with the worker lease renewed while waiting.

## Live integration findings on October 29, 2026

The locally configured key and Flash-Lite model answered a synthetic structured extraction request in about two seconds. Its one synthetic fact passed schema and evidence validation. This output was not inserted into the user's library.

The explicitly approved one-attempt Adani bill test returned structured output, but a local evidence rule rejected unsupported metadata. No facts from that response were saved. The source preview was preserved. Subsequent error diagnostics identify the fact and field that failed. No additional bill request was made after that validation failure. This is a known extraction-quality limitation, not an authentication failure or a completed dataset evaluation.

Restarting preserves requested work; retries do not re-upload the document. Source previews remain available even when the fact queue reports an error.

## 8. Demonstrate the milestone honestly

1. Open an already processed source document and inspect its source warnings.
2. Without a key, demonstrate the configuration message. This verifies the local guard, not a live model call.
3. With a valid key configured, click Extract facts for one document. Observe its independent queue state while source inspection remains available.
4. Inspect the returned classification and a small sample of facts. Follow page or cell references and review the entity, unit, and period in context.
5. Reload the page and confirm that the output persists. Repeat the extraction action only as the UI permits and explain its reuse/retry behavior.
6. Show a controlled mocked provider failure in tests to demonstrate retries and lease fencing. Label it as a test; do not mix mocked output with live results.
7. Record whether a real Gemini request was made and completed. If credentials or quota prevented it, report that limitation explicitly.

Tests of schema parsing, evidence rejection, queue deduplication, persistence, and recovery establish software behavior. They are not a labeled evaluation of extraction accuracy. Building the expected-answer dataset and measuring unsupported claims are later steps, alongside evidence-grounded QA and explicit fiscal-year handling. This milestone provisions no AWS resources.
