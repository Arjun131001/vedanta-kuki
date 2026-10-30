# Reviewing extracted facts: evidence, partial acceptance, and diagnostics

This guide explains the implemented v3 review design and how to demonstrate it without overstating accuracy. Local replay is implemented through the API and the review interface. Functional test results and live model results remain separate evidence.

## The observed v2 problem

The earlier live bill extraction reached local validation but was rejected because proposed metadata was not supported by its cited quotations under the v2 rules. The validator raised an error for the entire result. This establishes an observed integration failure; it does not establish that every candidate fact was incorrect, nor that every other candidate was correct.

V2 required label, unit, period, and currency strings to occur in the validated context. A paraphrased label or unsupported optional field could therefore discard otherwise usable candidates. The response format could be valid JSON while the application still rejected its contents.

Do not invent the discarded response, its accepted-fact count, or a more specific cause than the saved diagnostic establishes. If the complete candidate response was not retained, a later validator cannot replay that response locally.

## The v3 decision: validate candidates independently

V3 separates the evidence-supported core of a candidate from optional metadata. It preserves usable candidates while recording exactly what was rejected or removed. This changes the granularity of failure, not the requirement for source support.

| Component | Required evidence | On failure |
| --- | --- | --- |
| Reported value | A valid cited source quotation or cell containing the reported value, with its scale and qualifier preserved | Quarantine the candidate; do not include it in accepted facts |
| Source label | Exact source wording supported by a validated quotation | Quarantine the candidate |
| Page or sheet/cell location | Location exists in the request's persisted source snapshot | Quarantine the candidate when the core location is invalid |
| Optional unit | Supported source wording with dimension and case preserved | Clear the unsupported field and record an issue |
| Optional period or currency | Supported source wording | Clear the unsupported field and record an issue |
| Optional organization | Supported attribution text and evidence | Clear the unsupported field and record an issue |
| Display label | A readable model description, distinct from the exact source label | Treat it as interpretation, never as a verbatim quote |

A cleared field remains unknown. It is not zero, an empty fiscal year, or permission to inherit another entity's metadata. If all candidates fail their mandatory checks, the job should report a failure with diagnostics rather than a successful empty extraction. That is different from a valid response containing no candidate facts.

## Preserve exact source labels and honest interpretations

A bill may use a short label such as `Units`. A model might describe that as `Electricity consumption`. The application should keep `Units` as the evidence-supported source label and identify any longer display label as an interpretation. Matching the word `Units` alone does not establish that the measurement unit is kWh.

Separating the two labels avoids rejecting every readable paraphrase while also avoiding the opposite error: presenting a paraphrase as words printed in the original document.

## Normalize formatting without changing meaning

Whitespace normalization can tolerate line wrapping and repeated spaces. Numeric comparison can tolerate supported grouping separators when it preserves the same value. Neither permits adding a magnitude, changing a sign, removing a comparison qualifier, or assigning a missing unit.

For example, a quote containing `42` does not support the reported phrase `42 million`. A quoted value below a threshold must not silently become an exact measurement. Unit checks must distinguish `MWh` from `mWh`; case folding is not safe for every scientific symbol.

Do not map `units` to `kWh`, `$` to a particular dollar currency, or `Rs` to a specific currency code without the necessary source support. Preserve reported period text instead of deriving fiscal-year boundaries.

## Keep separate evidence pieces separate

A spreadsheet can put the value in `C8`, its label in `A8`, its unit in `C2`, and its period in `D1`. Each field can have its own validated source quotation and coordinates. A quotation must remain honest about where its words came from.

Validate field matches within individual evidence pieces. Concatenating unrelated quotations and searching the combined string can create a phrase that never appeared anywhere in the source. A matching quotation also does not prove that a header belongs to a particular value; a reviewer still needs to inspect the relationship.

## Record both the candidate and the decision

The review output should preserve the original structured candidate before any fields are cleared. For each candidate, retain its index, the accepted projection or rejection, and structured issues identifying the field, proposed value, reason, and cited evidence. Tie that audit to the source snapshot, model, prompt/schema version, and validator version.

This makes the decision explainable. A user can distinguish an unsupported numeric value from a valid amount whose period could not be established. The original proposal remains available for local debugging instead of being silently rewritten.

Audit records can contain source-sensitive information. Store them in the ignored local database alongside the extraction result. Do not publish real bill responses as repository fixtures or print their contents into ordinary logs. Synthetic fixtures can test the same behavior without being presented as actual model output.

The interface should distinguish accepted facts, facts with cleared fields, and rejected candidates. If exclusions or metadata removal reduce the result, mark coverage as partial and explain why. Use language such as `Evidence checks passed; review context`, rather than `Verified`, `Audited`, or `Accurate`.

## Recheck saved candidates locally

The review interface exposes a recheck action when a saved candidate response is available and the job is not active. Its endpoint is:

```text
POST /api/documents/{document_id}/facts/revalidate
```

`fact_queue.revalidate` parses the original `proposed_result` and the persisted request's `source_snapshot`, then runs the current local schema and evidence checks. It does not call Gemini, enqueue work, or require an API key. It updates the projected result and validator version while retaining the original proposed response and generation metadata. This replaces the current review; it does not retain an immutable history of every prior review.

The write checks that job status, prior result, and snapshot have not changed during review. If another operation changed them, it refuses to overwrite the newer state. The endpoint returns HTTP 409 for active jobs, missing/incompatible audit data, or a conflicting change, and HTTP 404 for an unknown document.

An all-rejected projection remains failed with its diagnostic candidates intact. If the saved proposal validates under the current rules, the projection can become ready. Source content is read from the request snapshot, so later edits to the current source tables do not alter the evidence used for replay.

The historical v2 failure cannot be replayed because it did not retain the necessary proposed response. A new model call would be a separate action, not a side effect of rechecking. Tests in `backend/tests/test_facts.py` cover replay without a key, snapshot isolation, retained rejection diagnostics, and unavailable old or active jobs. Report their actual test-run outcome separately from this implementation description.

## Demonstrate the fix without another model request

Start with the observed v2 failure and explain why document-wide rejection was too coarse. Then use clearly labeled synthetic candidates to demonstrate the local rules:

1. A valid value and exact source label are accepted.
2. A readable display-label paraphrase stays separate from the source label.
3. An unsupported optional period is cleared while the supported value remains, with a visible issue.
4. A fabricated numeric value or unsupported scale is quarantined.
5. A mixed result retains valid candidates and records rejected candidates; coverage is partial.
6. An all-invalid result reports failure with diagnostics rather than appearing successful.
7. Separate spreadsheet header/value references work, while a match assembled across unrelated quotes fails.
8. Audit records survive a restart. Use Recheck saved candidates to rerun the local validator without a key, and demonstrate the unavailable response for an old result without audit data.

For an interview, explain the boundary directly: “The model proposes facts. Deterministic checks reject unsupported source references and preserve review decisions. These checks improve traceability; they do not prove semantic accuracy.”

## What remains unproven

The v2 live failure is a baseline observation. Offline v3 tests establish validator and queue behavior; they are not a successful live v3 extraction and not a measurement of accuracy across the six documents. Until an explicitly authorized live run completes and its output is reviewed, make no live-success claim for v3.

Even after a successful run, labeled evaluation is needed to measure omitted facts, wrong interpretations, incorrect entity attribution, and unsupported claims. Fiscal-year aggregation and question answering remain separate future milestones.
