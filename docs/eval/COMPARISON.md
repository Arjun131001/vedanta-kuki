# QA evaluation: baseline vs improved

## Method

Eleven source-verified cases in `backend/evaluation/qa_cases.json` cover lookups, absence handling, waste/workbook calculations, Indian financial-year coverage, and cross-organisation refusal.

- **Baseline** simulates the pre-calculator behaviour: calculation and FY questions refuse with “calculation engine is not available yet.” Lookup/absence stubs remain grounded in assignment values.
- **Improved** uses the deterministic calculator in `backend/app/calculations.py` for calculation/FY cases. Lookup stubs are unchanged packaging placeholders; live OpenAI lookups remain the production path for non-calc questions.

Reproduce:

```powershell
cd backend
$env:PYTHONPATH = "."
..\.venv\Scripts\python.exe evaluation/run_qa_eval.py --mode baseline
..\.venv\Scripts\python.exe evaluation/run_qa_eval.py --mode offline --label improved
```

## Scores

| Run | Passed | Total | Score |
| --- | ---: | ---: | ---: |
| Baseline | 6 | 11 | 54.5% |
| Improved | 11 | 11 | 100% |

## What improved

- Waste quantity sum (`1.0 T + 0.4 T = 1.4 T`) is system-calculated with explicit operands.
- Workbook monthly vs annual reconciliation can sum retrieved monthly totals and compare to the reported annual figure.
- FY questions no longer hard-refuse; they filter by Indian FY bounds (1 Apr–31 Mar), report coverage, and refuse unsafe cross-organisation combined totals.
- Sparse FY evidence returns partial/none coverage language instead of inventing zeros.

## What regressed

- No scored regression in this offline package. Live lookup quality still depends on retrieval and the model; stubs are not a live accuracy claim.

## What remains unresolved

- OCR for the BESCOM image-only page.
- Live end-to-end scoring of lookup cases against the running OpenAI path.
- Organisation resolution beyond filename heuristics.
- Quarterly Summary annual total `2427123` vs Monthly Summary `2425123` conflict needs explicit surfacing when both sheets are retrieved.
