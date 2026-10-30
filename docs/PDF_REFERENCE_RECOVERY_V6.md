# PDF proposal recovery, validator v6

Applied locally on 30 October 2026 without provider requests. Previous outputs
and immutable proposals remain in extraction history.

| PDF | Rejected before | Rejected after |
| --- | ---: | ---: |
| Water bill invoice | 25 | 3 |
| Nestle quality policy | 1 | 1 |
| Adani commercial electricity bill | 21 | 16 |
| Form 3 | 2 | 2 |
| BESCOM commercial electricity bill | 0 | 0 |
| Total | 49 | 22 |

Twenty-seven proposals were recovered for review, not promoted to checked
facts. Existing checked fact counts remained unchanged for these PDFs.

Recovery handles a literal value mistakenly used as a reference only when the
resolved label line is a segment target and contains the exact proposed value.
Existing numeric qualifier and scale checks still run. It does not use a label
on another page or a value found only in context.

Label formatting recovery locates a unique substring on the cited PDF line
that differs only in case or whitespace. The projected source label retains
the exact extracted source substring. Original wording, source wording and
references are audited; the proposal itself is unchanged. Short, numeric-only,
ambiguous and partial-word matches are excluded. Interpretation remains subject
to review, including cases where spacing could change word meaning.

Remaining rejections include empty values, unsupported labels or statements,
invalid multiline spans, non-target evidence and out-of-scope contact data.
Changing a rejection count does not correct these underlying problems. Zero
rejections is not an accuracy or completeness guarantee.

Verification: 22 focused regression tests passed, covering PDF formatting,
literal reference mistakes, fabricated values, missing data, page boundaries,
ambiguous labels, numeric qualifiers/scales, workbook recovery, source integrity,
and existing exact PDF reference recovery. Full application verification and
new model extraction were not performed.
