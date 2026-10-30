export type OverviewFact = {
  label: string;
  source_label: string;
  value: string;
  unit: string | null;
  organization?: string | null;
};
export function topicFor(fact: OverviewFact): string;
export function highlightKind(fact: OverviewFact): string | null;
export function findMeterPair<T extends OverviewFact>(
  checked: T[],
  review: T[],
): { fact: T; status: "checked" | "review"; numeric: number }[] | null;
export function buildOverview<T extends OverviewFact>(
  checked: T[],
  review: T[],
): {
  topics: { name: string; count: number }[];
  highlights: { fact: T; status: "checked" | "review"; kind: string }[];
  commitments: { fact: T; status: "checked" | "review" }[];
  meterPair:
    { fact: T; status: "checked" | "review"; numeric: number }[] | null;
};
