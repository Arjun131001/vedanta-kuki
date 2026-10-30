# Authorized PDF extraction trial, 30 October 2026

All 20 planned OpenAI requests completed without request failures. The initial
restricted-network attempt failed at DNS resolution before reaching the API;
the trial then ran with network access following the user's explicit approval.
No additional model repair requests were made.

## Applied results

| PDF | Before trial | Current rejected | Current checked | Current review |
| --- | ---: | ---: | ---: | ---: |
| Water bill invoice | 3 | 0 | 28 | 1 |
| Nestle quality policy | 1 | 0 | 31 | 1 |
| BESCOM electricity bill | 0 | 0 | 18 | 0 |
| Adani electricity bill | 16 | 15 | 13 | 12 |
| Form 3 | 2 | 2 | 2 | 1 |
| Total | 22 | 17 | 92 | 15 |

Zero was achieved for three of five PDFs, not all five. Remaining proposals
still fail source support, target ownership or evidence-span checks. They have
not been hidden or accepted to meet a count target.

The water bill and quality policy improvements were imported atomically into
the local application. Previous jobs and segment snapshots were archived.
Source snapshots were checked for equality, active jobs were excluded, and
concurrent changes caused an abort rather than an overwrite.

The water trial omitted one previously checked rebate policy. Its original
proposal was retained separately from immutable new provider output, with
the original request/segment recorded, and passed current evidence checks.
Saved revalidation and offline replay include retained proposals. No previous
checked value was lost from either imported document. This is a regression
check against prior output, not proof that every relevant fact was extracted.

## Trial limitations

Raw trial rejections were: water 1, quality 0, BESCOM 20, Adani 41, Form 3 2.
The new schema prevents nonexistent IDs but cannot prevent the model from
choosing an existing ID with unrelated text. Smaller segments did not reliably
reduce these semantic reference errors. Electricity-bill and Form 3 trial runs
were preserved separately instead of replacing the better existing results.

Validator v7 adds narrow PDF label-prefix recovery: the retained shorter label
must itself be a verbatim, multiword prefix present on the cited source line.
The unsupported suffix is audited, and the candidate stays in review. It also
locates uniquely matching case/spacing variants of labels within the same
submitted segment and cited page. Ambiguous and cross-page matches remain
rejected. These rules recovered the water-bill wrapped label and one additional
Adani header without another provider call.

Thirty-six focused regression tests passed, including fabrication, ambiguity,
page and target boundaries, qualifiers/scales, immutable proposals, retained
proposal replay, source-bound schemas and source extraction integrity.
This was not a full application test run or an independent semantic audit.

Detailed source-containing trial artifacts are stored only in the ignored
`tmp/source-bound-pdf-trial/` directory. No credentials are included in reports.
