# Reducing rejected proposals

Validator v5 can locate a uniquely matching spreadsheet label or value in the
submitted segment on the originally cited sheet. Value recovery is restricted to
segment targets. Sheet titles, missing formula caches, ambiguous matches, and
matches on other sheets cannot establish evidence. Existing numeric qualifier
and scale checks still apply.

Recovered proposals remain review candidates, with original and resolved IDs in
the recovery audit. They are not automatically accepted facts. Original model
proposals remain unchanged. Rechecking saved results uses no provider calls.

Prompt v9 adds explicit checks for empty values, header versus value references,
exact source wording, contiguous PDF spans, and target IDs. It asks the extractor
to report unsupported coverage as a gap rather than fabricate a proposal. Its
effect on future provider output has not been measured.

Local replay on 30 October 2026 reduced 209 saved rejections to 94, recovering
115 workbook proposals for review; the workbook went from 160 to 45 rejections.
At segment level, checked facts were unchanged. Revalidation was applied to the
local workbook, preserving the previous output in history. Document aggregation
also detected metadata conflicts between recovered proposals and existing facts,
moving those facts to review. The resulting workbook has 136 checked facts,
188 review candidates, and 45 rejected proposals. These counts measure evidence recovery, not
semantic accuracy or exhaustive extraction. Empty values, ambiguous evidence,
and unsupported claims still require correction or a new extraction.

Thirteen focused regression tests passed, including ambiguity, sheet/target
boundaries, fabricated values, provider schema, PDF recovery, and source integrity.
No live provider calls were made for this verification.
