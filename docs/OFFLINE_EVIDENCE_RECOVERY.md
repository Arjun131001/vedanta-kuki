# Offline evidence-reference recovery

## Problem and design

The first OpenAI Adani run completed all four segments but produced 35 rejected proposals. Several proposals contained a supported value and exact source label but referenced the wrong line. Others repeated an identical reference twice or cited unsupported optional metadata. Changing providers alone did not solve extraction accuracy.

The local validator now supports conservative recovery against the immutable segment snapshot:

- Collapse adjacent duplicate IDs, while preserving the original list in the recovery audit. Do not reorder references or fill gaps.
- Locate an unchanged source label or value only if its exact text has one unambiguous matching line/span in the submitted segment and originally cited PDF page. Spans remain bounded to eight consecutive lines within one reading block.
- Keep value references restricted to segment targets. Do not use another page, another document, fuzzy similarity, nearest numbers, inferred labels, changed values, or missing formula caches.
- Apply all existing numeric-boundary, sign, scale, qualifier, and source checks after resolving a reference.
- Put recovered proposals exclusively in `review_candidates`, even if the repaired label and value share a line. A repaired reference does not prove their relationship.
- Clear unsupported optional metadata with a field-specific issue instead of rejecting an otherwise supported core value.
- Reject obvious contact-detail proposals as outside scope, while preserving policy commitments that mention contact channels.

Each recovered candidate exposes its one-based proposal index, method, original IDs, recovered IDs, and recovery reason. The frontend shows these changes beside its source evidence. Original model proposals remain unchanged.

## Durable audit and OpenAI-only execution

Local revalidation archives the previous job and all segment projections, with before/after result hashes and validator version. Repeating unchanged validation does not create duplicate audit entries. A transaction and concurrency checks prevent replacing a result that changed during replay.

The active model adapter is OpenAI only. Obsolete Gemini settings were removed from the ignored local environment file. Legacy-provider migration tags, tests, and historical results remain intentionally: they preserve provenance and prevent old jobs being sent through a different provider. No Gemini executable adapter remains.

## Reproducible comparison

Run from the repository root before applying a changed validator:

```powershell
.\.venv\Scripts\python.exe backend/evaluation/replay_saved_evidence.py --database backend/data/documents.sqlite3 --document-id YOUR_DOCUMENT_ID --output tmp/offline-replay.json
```

This tool opens SQLite read-only, replays saved proposals locally, and records category counts, rejection reasons, review methods, and immutable-proposal hashes. It does not instantiate a provider client or enqueue jobs. Detailed private experiment outputs remain ignored under `tmp/`.

On the same saved four OpenAI responses, the projection changed from 6 checked / 0 review / 35 rejected to 9 checked / 11 review / 21 rejected. The total remains 41 proposals. The increase in checked proposals comes from handling unsupported optional metadata separately; recovered references always remain in review. Two formerly checked contact details are now rejected as irrelevant. This is an intentional scope correction, not a claim that rejected proposals became accurate.

The current-month amount and units consumed were recovered using the exact page-one header and unchanged value row. Their association remains for review. The unchanged consumption probe already accepts the manually checked summary on page one or consumption table on page two; no cross-page recovery or evaluation-case change was needed.

The same twelve source-verified probes changed as follows:

| Stage | Matched | Needs review | Missing | Not completed |
| --- | ---: | ---: | ---: | ---: |
| Saved OpenAI baseline | 5 | 2 | 3 | 2 |
| Offline recovery | 5 | 4 | 1 | 2 |

Both Adani probes moved from missing to review. No probe category regressed. Oil residue remains missing, and two policy probes remain incomplete. Counts refer to evidence-validation outcomes, not semantic correctness.

## Verification

All 72 backend tests passed, including mixed single-line/split-line ambiguity, overlapping-window occurrence deduplication, cross-page and target restrictions, missing formula caches, qualifiers, optional metadata, contact relevance, and blank proposals. The frontend production build and five upload tests passed.

Persisted local revalidation returned `ready` with validator `facts-index-validation-v3`. All four saved proposal hashes matched their baseline hashes. The previous projection and segment snapshots are archived with distinct before/after hashes; a second identical revalidation created no duplicate archive. No other document was revalidated or sent to a model.

## Limits

Unambiguous source text is evidence of location, not semantic correctness. Misread values, fabricated labels, ambiguous matches, conflicting periods or organisations, omitted facts, and scope interpretation still require further work. This experiment improves the evidence validator, not the model's original response. No document was resent and no model request was made during this improvement. These extraction checks do not replace the assignment's final source-verified question-answering evaluation.
