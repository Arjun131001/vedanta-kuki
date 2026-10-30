# Coverage and evidence improvements

## Design

The worker creates persistent segment manifests: up to 80 PDF lines with nearby context, or four populated workbook rows with header context. Every nonempty workbook cell is a primary target exactly once. Oversized segments fail explicitly rather than silently truncating content. Segment status, attempts, responses, and failures survive restarts. Completed segments are skipped when resuming failed jobs.

Operational coverage is separate from extraction quality: processing every target does not mean every fact was extracted. Evidence spans are limited to eight consecutive lines within one page and reading block. A conservative narrative-column detector preserves bounding boxes and original text. It detected only page three of the supplied policy; a local word-multiset comparison found no added or lost words, and a reconstructed policy commitment passed local evidence validation.

Workbook literals now explicitly identify themselves as available values; only formulas use cached-value metadata. A local fallback exposes unmentioned numeric cells under explicit same-column metric headers as review candidates with exact references. It does not infer periods, accept relationships, or calculate totals. The UI distinguishes these locally mapped cells from AI proposals.

## Results

The approved six-document batch used exactly 35 Gemini requests without retries: Adani 4, workbook 22, BESCOM 1, waste form 2, policy 3, water 3. All returned responses. The workbook manifest covered all 557 nonempty cells. Results were 48 automatically checked facts, 257 review candidates, and 56 rejected proposals. These are validation categories, not accuracy scores. Earlier runs and source snapshots were preserved.

The separately approved policy retest used three requests, one per page, without retries. Two completed; page three returned a temporary provider availability or rate-limit error. The policy job remains failed with partial coverage. Live extraction of its corrected third page is unverified. No other document was resent.

Offline workbook revalidation added 46 locally mapped review candidates: the workbook now has 14 checked facts, 297 review candidates, and 49 rejected proposals. January's F3 total is visible for review. This required no additional Gemini requests.

| Fixed source-checked probes | Matched | Needs review | Missing | Not completed |
| --- | ---: | ---: | ---: | ---: |
| Prior evidence-ID baseline | 5 | 2 | 3 | 2 |
| 35-segment run | 6 | 2 | 2 | 2 |
| Final offline fixes | 6 | 3 | 1 | 2 |

Adani consumption moved from review to matched. Workbook annual total moved from missing to review; January total subsequently moved from missing to review. Oil residue remains missing, and both policy probes remain incomplete. No probe category regressed. This small set cannot establish general semantic accuracy or exclude other regressions; candidate counts alone do not measure quality.

## Verification and remaining work

All 59 backend tests passed with mocked provider calls. The frontend production build and five upload tests passed. Tests cover persistent segments/resume, manifests, bounded spans, column boundaries, literal/cache distinctions, and conservative fallback.

Unresolved: oil-residue extraction, label/value relationships, policy completion, and OCR for a BESCOM image-only page. Column detection is a heuristic, not a general layout engine. Checked evidence still requires semantic review before totals or answers. These twelve extraction probes are not the final QA evaluation. QA, Indian financial years, organisation resolution, overlap handling, and the source-verified QA baseline/improvement comparison remain future milestones.

Raw responses, experiment outputs, documents, credentials, and databases remain ignored by Git.
