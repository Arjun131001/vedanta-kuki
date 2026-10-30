# Preventing invalid proposals during extraction

Prompt v10 and request schema `source-bound-references-v1` constrain new model
requests to the submitted source IDs. `value_ref` must be a usable target ID;
other references must be usable source IDs. Missing formula caches, blank
records and spreadsheet error cells are excluded from reference enums. Required
labels and values must contain a non-whitespace character. Local evidence,
numeric qualifier, scale, scope and span validation still run independently.

Enums use shared definitions rather than repeating long lists for every field.
Requests are rejected locally before sending if they have no usable targets or
would exceed the reference budget. The schema version and exact per-request
schema hash are stored alongside model output for audit. Request fingerprints
change so old saved outputs cannot be mistaken for output from these constraints.

These constraints use the supported enum and string constraints described in
[OpenAI's structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat).
They constrain output shape and reference membership, not factual correctness.

PDF segmentation v3 uses at most 40 target lines per request, keeps independent
reading blocks separate, and includes up to seven neighboring context lines
within the same block. Every nonempty PDF record remains a target exactly once;
context does not count as additional coverage. This leaves more space below the
60-fact cap for lines containing multiple quantities. It may increase provider
request count; the plan remains visible before extraction.

Local verification covers reference/target separation, missing caches and error
cells, request-schema isolation, provider body construction, size limits, exact
target coverage, block boundaries, PDF recovery, and fabricated evidence.
All five saved PDFs pass local request-schema preflight across 20 planned calls.

The user authorized a live trial after the initial automatic approval block.
Twenty provider calls completed successfully on 30 October 2026. Trial output
was saved separately; existing outputs were not replaced indiscriminately.
See [live results](PDF_LIVE_TRIAL.md). Zero rejections across all PDFs and
complete semantic extraction have not been established.
