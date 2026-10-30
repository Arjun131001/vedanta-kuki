# Evidence-ID extraction comparison — 29 October 2026

This is an extraction experiment, not the assignment's final question-answering evaluation. The twelve probes in `backend/evaluation/extraction_expectations.json` were checked against the local source documents. The checker reads saved API output and does not call Gemini. Numeric/label/location matches still require semantic review.

## Change tested

Previously Gemini had to regenerate exact quotations. The improved prompt receives a deterministic index of PDF lines and spreadsheet cells and cites IDs. The backend resolves each ID against the frozen source snapshot, preserving exact text and checking values, labels, units, and qualifiers. Same-record claims that pass checks become checked facts; cross-record associations remain review candidates. Unknown references or unsupported core values are rejected.

Before replacing a result, the prior result and source snapshot are archived in the local database. The prior Adani result remains available through the history API. No real model responses, keys, or uploaded files are committed to Git.

## Approved live run

The user authorized one attempt per supplied document using Gemini 3.5 Flash-Lite. Automatic retries were disabled for the batch. All six returned structured output; one had no proposals that passed core evidence checks. Every result has partial coverage.

| Document | Checked facts | Needs review | Rejected |
| --- | ---: | ---: | ---: |
| Adani bill | 2 | 4 | 2 |
| Annual electricity workbook | 0 | 15 | 0 |
| BESCOM bill | 8 | 0 | 0 |
| Waste Form 3 | 2 | 0 | 2 |
| Quality policy | 0 | 0 | 1 |
| Water invoice | 7 | 0 | 3 |
| **Total** | **19** | **19** | **8** |

The prior Adani run had zero checked facts, one locally recovered review candidate, and two rejected proposals. The new run has more usable source references, but it is not an apples-to-apples accuracy percentage: the model proposed a different number of facts. A complete six-document baseline was not previously run, so no six-document baseline improvement percentage is claimed.

## Fixed source probes

| Probe | Result |
| --- | --- |
| Adani consumption | Needs review |
| Adani current bill amount | Needs review |
| Workbook January total at Monthly Summary 2026!F3 | Missing |
| Workbook annual total at Monthly Summary 2026!F16 | Missing at requested location |
| BESCOM consumption | Matched |
| BESCOM net payable | Matched |
| Water consumption | Matched |
| Water amount due | Matched |
| ETP sludge quantity | Matched |
| Oil-residue waste quantity | Missing |
| Policy value-chain scope | Not completed |
| No invented complaint-resolution deadline | Not completed; policy failed core validation |

Summary: **5 matched, 2 needing review, 3 missing, 2 not completed**. Adani consumption is reported on both pages; either source page is valid. The workbook's annual consumption was proposed from another summary sheet, but that does not satisfy a probe targeting a specific cell. The checker distinguishes the worksheet as well as the cell address.

## What remains unresolved

- The model selected annual summary content and omitted the requested monthly-detail cells. Per-sheet or bounded row-group requests with explicit coverage tracking are a better next experiment than claiming whole-workbook coverage.
- Waste labels and policy commitments span PDF lines. Current single-reference values/labels cannot safely represent all such text. Bounded multi-line evidence spans should retain exact locations, rather than allowing invented concatenations.
- BESCOM's image-only page still has no OCR text and remains flagged.
- Reference validity is not proof of correct metric/entity association. Cross-record candidates must stay outside automatic aggregation.
- No source-verified QA answers, FY totals, final accuracy score, or ten-case QA baseline/improved comparison is claimed.

## Reproduce

With the services running and original files available locally, run from `backend`:

```powershell
..\.venv\Scripts\python.exe evaluation/check_extraction.py "C:\path\to\kuki-assignment-dataset"
```

The report is written under ignored `tmp/`. Rerunning this checker makes no model requests. Live extraction is a separate manual action. Final verification: **47 backend tests**, **5 upload tests**, and frontend production build passed.
