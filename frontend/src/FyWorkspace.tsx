import { useEffect, useMemo, useState } from "react";
import Select from "./Select";

type Doc = { id: string; filename: string; status: string };
type ReportedValue = {
  value: string;
  unit?: string;
  filename?: string;
  period_start?: string | null;
  period_end?: string | null;
  label?: string;
  citation_id?: string;
};

type FySummary = {
  year: number;
  bounds: [string, string];
  coverage: string;
  totals: {
    unit: string;
    value: string;
    operand_count: number;
    reported_values?: ReportedValue[];
  }[];
  items: ReportedValue[];
  excluded_notes: string[];
  limitations: string[];
  warnings?: string[];
  answer: string;
};

const api = import.meta.env.VITE_API_URL || "";

export default function FyWorkspace({
  docs,
  online,
  onOpenSource,
}: {
  docs: Doc[];
  online: boolean;
  onOpenSource: (documentId: string) => void;
}) {
  const ready = useMemo(() => docs.filter((d) => d.status === "ready"), [docs]);
  const [year, setYear] = useState(2024);
  const [selected, setSelected] = useState<string[]>([]);
  const [summary, setSummary] = useState<FySummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    if (!selected.length || busy || !online) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${api}/api/fy/summary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ year, document_ids: selected }),
      });
      if (!response.ok) {
        let detail = "Could not build the financial-year summary.";
        try {
          const body = await response.json();
          if (typeof body.detail === "string") detail = body.detail;
        } catch {
          /* ignore */
        }
        throw Error(detail);
      }
      setSummary(await response.json());
    } catch (err) {
      setSummary(null);
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  function toggle(id: string) {
    setSelected((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : current.length >= 10 ? current : [...current, id],
    );
  }

  return (
    <section className="fy-workspace" aria-labelledby="fy-title">
      <div className="fy-hero">
        <div className="section-kicker">FINANCIAL YEAR</div>
        <h2 id="fy-title">Coverage and calculated totals</h2>
        <p>
          Indian financial years run April–March. A <strong>reported value</strong> is a figure taken from a
          document (bill, invoice, or sheet). A <strong>calculated total</strong> is this app summing those
          reported values for the selected FY — it is not copied as a pre-printed FY total from the file.
        </p>
      </div>

      <div className="fy-controls">
        <label>
          FY start year
          <Select label="Financial year start" value={String(year)} onChange={(value) => setYear(Number(value))}
            options={[2023, 2024, 2025, 2026].map((value) => ({ value: String(value), label: `FY ${value}-${String(value + 1).slice(-2)}` }))} />
        </label>
        <button className="primary-button" disabled={!selected.length || busy || !online} onClick={() => void run()}>
          {busy ? "Calculating…" : "Calculate coverage"}
        </button>
      </div>

      <div className="fy-picker">
        <strong>Select documents</strong>
        {!ready.length && <p className="fy-empty">No extracted documents yet. Upload and process files in the library first.</p>}
        <div className="fy-doc-grid">
          {ready.map((doc) => (
            <label key={doc.id} className={selected.includes(doc.id) ? "selected" : ""}>
              <input
                type="checkbox"
                checked={selected.includes(doc.id)}
                onChange={() => toggle(doc.id)}
                aria-label={`Include ${doc.filename}`}
              />
              <span>{doc.filename}</span>
            </label>
          ))}
        </div>
      </div>

      {error && (
        <p className="fy-error" role="alert">
          {error}
        </p>
      )}

      {summary && (
        <div className="fy-results">
          <div className="fy-coverage">
            <span className={`fy-pill ${summary.coverage}`}>{summary.coverage} coverage</span>
            <p>
              Bounds {summary.bounds[0]} → {summary.bounds[1]}
            </p>
          </div>
          <div className="fy-totals">
            {summary.totals.length ? (
              summary.totals.map((total) => {
                const reported =
                  total.reported_values?.length
                    ? total.reported_values
                    : summary.items.filter((item) => (item.unit || "") === total.unit);
                return (
                  <article key={total.unit}>
                    <small>Calculated total (system sum)</small>
                    <strong>
                      {total.value} {total.unit}
                    </strong>
                    <span>
                      Sum of {total.operand_count} reported value
                      {total.operand_count === 1 ? "" : "s"} from your documents
                    </span>
                    {reported.length > 0 && (
                      <div className="fy-reported-list">
                        <p className="fy-reported-heading">Reported values used</p>
                        <ul>
                          {reported.map((item, index) => {
                            const doc = item.filename
                              ? ready.find((d) => d.filename === item.filename)
                              : undefined;
                            return (
                              <li key={`${item.citation_id || item.value}-${index}`}>
                                <button
                                  type="button"
                                  className="fy-reported-item"
                                  disabled={!doc}
                                  onClick={() => doc && onOpenSource(doc.id)}
                                >
                                  <strong>
                                    {item.value}
                                    {item.unit ? ` ${item.unit}` : total.unit ? ` ${total.unit}` : ""}
                                  </strong>
                                  <span>{item.label || item.filename || "Source document"}</span>
                                  <small>
                                    {item.filename ? `${item.filename} · ` : ""}
                                    {item.period_start || "period unknown"}
                                    {item.period_end ? ` → ${item.period_end}` : ""}
                                  </small>
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    )}
                  </article>
                );
              })
            ) : (
              <p className="fy-empty">No same-unit totals could be calculated for this year.</p>
            )}
          </div>
          <div className="fy-items">
            <h3>All included reported values</h3>
            <p className="fy-help">
              These are the document figures matched to this FY. The calculated totals above add values that share
              the same unit.
            </p>
            {summary.items.length ? (
              <ul>
                {summary.items.map((item, index) => (
                  <li key={`${item.citation_id || item.label}-${index}`}>
                    <button type="button" onClick={() => item.filename && ready.find((d) => d.filename === item.filename) && onOpenSource(ready.find((d) => d.filename === item.filename)!.id)}>
                      <strong>
                        {item.value}
                        {item.unit ? ` ${item.unit}` : ""}
                      </strong>
                      <span>{item.label ? `${item.label} · ` : ""}{item.filename}</span>
                      <small>
                        {item.period_start || "period unknown"}
                        {item.period_end ? ` → ${item.period_end}` : ""}
                      </small>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="fy-empty">No period-matched values were included.</p>
            )}
          </div>
          {(summary.excluded_notes.length > 0 || summary.limitations.length > 0) && (
            <details className="fy-notes" open>
              <summary>Assumptions and limitations</summary>
              {[...summary.excluded_notes, ...summary.limitations].map((note, index) => (
                <p key={index}>{note}</p>
              ))}
            </details>
          )}
        </div>
      )}
    </section>
  );
}

type EvalCase = { id: string; pass: boolean; notes?: string };
type EvalOverall = { score?: number; passed?: number; total?: number };
type EvalBundle = { overall?: EvalOverall; cases?: EvalCase[] } | null;

const CASE_META: Record<string, { title: string; category: string; blurb: string }> = {
  adani_consumption_period: {
    title: "Adani consumption & period",
    category: "Lookup",
    blurb: "Find reported kWh and billing period on the Adani bill.",
  },
  bescom_consumption_period: {
    title: "BESCOM consumption & period",
    category: "Lookup",
    blurb: "Find reported consumption and period on the BESCOM bill.",
  },
  water_consumption: {
    title: "Water consumption",
    category: "Lookup",
    blurb: "Report water use and check meter-reading support.",
  },
  waste_total_sum: {
    title: "Waste quantity sum",
    category: "Calculation",
    blurb: "Add recorded waste quantities with a system calculation.",
  },
  workbook_monthly_vs_annual: {
    title: "Workbook monthly vs annual",
    category: "Calculation",
    blurb: "Sum monthly figures and compare to the annual total.",
  },
  policy_complaint_deadline_absent: {
    title: "Complaint deadline absent",
    category: "Absence",
    blurb: "Do not invent a deadline the policy does not state.",
  },
  policy_value_chain_scope: {
    title: "Policy value-chain scope",
    category: "Lookup",
    blurb: "Retrieve the quality policy’s stated scope wording.",
  },
  fy_2024_electricity_bills: {
    title: "FY 2024 electricity coverage",
    category: "Financial year",
    blurb: "Filter bills into Indian FY 2024-25 and handle org separation.",
  },
  fy_2025_sparse_water: {
    title: "FY 2025 sparse coverage",
    category: "Financial year",
    blurb: "State partial/none coverage instead of inventing totals.",
  },
  cross_org_refuse_blind_total: {
    title: "Refuse blind cross-org total",
    category: "Safety",
    blurb: "Refuse combining Adani + BESCOM into one unsafe total.",
  },
  missing_metric_limitation: {
    title: "Missing emissions metric",
    category: "Absence",
    blurb: "Admit Scope 1 GHG is not on the water bill.",
  },
};

function ScoreRing({
  label,
  score,
  passed,
  total,
  tone,
}: {
  label: string;
  score: number;
  passed: number;
  total: number;
  tone: "baseline" | "improved";
}) {
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const capped = Math.max(0, Math.min(100, score));
  const offset = circumference - (capped / 100) * circumference;
  return (
    <article className={`eval-ring-card ${tone}`}>
      <svg viewBox="0 0 140 140" className="eval-ring" aria-hidden="true">
        <circle className="eval-ring-track" cx="70" cy="70" r={radius} />
        <circle
          className="eval-ring-value"
          cx="70"
          cy="70"
          r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="eval-ring-copy">
        <small>{label}</small>
        <strong>{capped.toFixed(capped % 1 ? 1 : 0)}%</strong>
        <span>
          {passed}/{total} cases passed
        </span>
      </div>
    </article>
  );
}

function ComparisonBars({ baseline, improved }: { baseline: number; improved: number }) {
  const max = Math.max(baseline, improved, 1);
  return (
    <div className="eval-bars" role="img" aria-label={`Baseline ${baseline} percent, improved ${improved} percent`}>
      <div className="eval-bar-row">
        <span>Baseline</span>
        <div className="eval-bar-track">
          <div className="eval-bar-fill baseline" style={{ width: `${(baseline / max) * 100}%` }} />
        </div>
        <strong>{baseline}%</strong>
      </div>
      <div className="eval-bar-row">
        <span>Improved</span>
        <div className="eval-bar-track">
          <div className="eval-bar-fill improved" style={{ width: `${(improved / max) * 100}%` }} />
        </div>
        <strong>{improved}%</strong>
      </div>
    </div>
  );
}

function CategoryChart({
  categories,
}: {
  categories: { name: string; baselinePass: number; improvedPass: number; total: number }[];
}) {
  const width = 520;
  const height = 220;
  const pad = { top: 20, right: 16, bottom: 42, left: 36 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const groupW = innerW / Math.max(categories.length, 1);
  const barW = Math.min(22, groupW * 0.32);

  return (
    <svg className="eval-category-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Pass counts by category">
      {[0, 0.25, 0.5, 0.75, 1].map((tick) => {
        const y = pad.top + innerH * (1 - tick);
        const maxTotal = Math.max(...categories.map((c) => c.total), 1);
        return (
          <g key={tick}>
            <line x1={pad.left} x2={width - pad.right} y1={y} y2={y} className="eval-grid" />
            <text x={pad.left - 8} y={y + 4} className="eval-axis">
              {Math.round(maxTotal * tick)}
            </text>
          </g>
        );
      })}
      {categories.map((cat, index) => {
        const maxTotal = Math.max(...categories.map((c) => c.total), 1);
        const x = pad.left + index * groupW + groupW / 2;
        const bH = (cat.baselinePass / maxTotal) * innerH;
        const iH = (cat.improvedPass / maxTotal) * innerH;
        return (
          <g key={cat.name}>
            <rect
              className="eval-cat-baseline"
              x={x - barW - 4}
              y={pad.top + innerH - bH}
              width={barW}
              height={bH}
              rx="4"
            />
            <rect
              className="eval-cat-improved"
              x={x + 4}
              y={pad.top + innerH - iH}
              width={barW}
              height={iH}
              rx="4"
            />
            <text x={x} y={height - 14} textAnchor="middle" className="eval-cat-label">
              {cat.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function EvalComparisonPanel() {
  const [data, setData] = useState<{
    available: boolean;
    message?: string;
    baseline: EvalBundle;
    improved: EvalBundle;
  } | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<"all" | "fixed" | "steady" | "regress">("all");

  useEffect(() => {
    void fetch(`${api}/api/eval/comparison`)
      .then(async (response) => {
        if (!response.ok) throw Error("Could not load evaluation comparison.");
        setData(await response.json());
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load evaluation comparison."));
  }, []);

  const rows = useMemo(() => {
    if (!data?.available) return [];
    const improvedCases = data.improved?.cases || [];
    return improvedCases.map((item) => {
      const before = data.baseline?.cases?.find((c) => c.id === item.id);
      const baselinePass = Boolean(before?.pass);
      const improvedPass = Boolean(item.pass);
      const change =
        !baselinePass && improvedPass
          ? "fixed"
          : baselinePass && improvedPass
            ? "steady"
            : baselinePass && !improvedPass
              ? "regress"
              : "fail";
      return {
        ...item,
        baselinePass,
        improvedPass,
        change,
        meta: CASE_META[item.id] || {
          title: item.id.replace(/_/g, " "),
          category: "Other",
          blurb: item.notes || "",
        },
      };
    });
  }, [data]);

  const categories = useMemo(() => {
    const names = ["Lookup", "Calculation", "Financial year", "Absence", "Safety"];
    return names
      .map((name) => {
        const group = rows.filter((row) => row.meta.category === name);
        return {
          name,
          total: group.length,
          baselinePass: group.filter((row) => row.baselinePass).length,
          improvedPass: group.filter((row) => row.improvedPass).length,
        };
      })
      .filter((item) => item.total > 0);
  }, [rows]);

  if (error) return <p className="fy-error">{error}</p>;
  if (!data) return <p className="fy-empty">Loading evaluation comparison…</p>;
  if (!data.available) {
    return (
      <section className="eval-panel">
        <div className="section-kicker">EVALUATION</div>
        <h2>Baseline vs improved</h2>
        <p>{data.message || "Scorecards are not available yet."}</p>
      </section>
    );
  }

  const baseline = data.baseline?.overall;
  const improved = data.improved?.overall;
  const baselineScore = baseline?.score ?? 0;
  const improvedScore = improved?.score ?? 0;
  const delta = Math.round((improvedScore - baselineScore) * 10) / 10;
  const fixedCount = rows.filter((row) => row.change === "fixed").length;
  const filtered = rows.filter((row) => filter === "all" || row.change === filter);

  return (
    <section className="eval-panel" aria-labelledby="eval-title">
      <div className="eval-hero">
        <div className="section-kicker">EVALUATION</div>
        <h2 id="eval-title">How quality was measured</h2>
        <p>
          This panel is a saved report of the assignment’s offline QA suite — not a live re-run on every click. Eleven
          fixed cases check lookups, calculations, Indian FY handling, absence answers, and unsafe-total refusals.
        </p>
      </div>

      <ol className="eval-flow">
        <li>
          <strong>1. Fixed cases</strong>
          <span>11 source-verified questions in `qa_cases.json`.</span>
        </li>
        <li>
          <strong>2. Baseline</strong>
          <span>Before the calculator — calc/FY questions refuse.</span>
        </li>
        <li>
          <strong>3. Improved</strong>
          <span>Same cases after deterministic calc/FY logic.</span>
        </li>
        <li>
          <strong>4. Compare</strong>
          <span>Pass/fail + notes packaged in committed scorecards.</span>
        </li>
      </ol>

      <div className="eval-scoreboard">
        <ScoreRing
          label="Baseline"
          tone="baseline"
          score={baselineScore}
          passed={baseline?.passed ?? 0}
          total={baseline?.total ?? 0}
        />
        <div className="eval-delta-card">
          <small>Lift after improvement</small>
          <strong className={delta >= 0 ? "up" : "down"}>
            {delta >= 0 ? "+" : ""}
            {delta} pts
          </strong>
          <ComparisonBars baseline={baselineScore} improved={improvedScore} />
          <p>
            <span className="eval-chip fixed">{fixedCount} fixed</span>
            <span className="eval-chip steady">
              {rows.filter((row) => row.change === "steady").length} still passing
            </span>
          </p>
        </div>
        <ScoreRing
          label="Improved"
          tone="improved"
          score={improvedScore}
          passed={improved?.passed ?? 0}
          total={improved?.total ?? 0}
        />
      </div>

      <div className="eval-chart-block">
        <div className="eval-chart-head">
          <h3>Pass count by category</h3>
          <div className="eval-legend">
            <span>
              <i className="legend-baseline" /> Baseline
            </span>
            <span>
              <i className="legend-improved" /> Improved
            </span>
          </div>
        </div>
        <CategoryChart categories={categories} />
        <div className="eval-category-cards">
          {categories.map((cat) => (
            <article key={cat.name}>
              <strong>{cat.name}</strong>
              <div className="eval-mini-meter" aria-hidden="true">
                <span style={{ width: `${(cat.baselinePass / cat.total) * 100}%` }} className="baseline" />
                <span style={{ width: `${(cat.improvedPass / cat.total) * 100}%` }} className="improved" />
              </div>
              <small>
                {cat.baselinePass}/{cat.total} → {cat.improvedPass}/{cat.total}
              </small>
            </article>
          ))}
        </div>
      </div>

      <div className="eval-cases-head">
        <h3>Case outcomes</h3>
        <div className="eval-filters" role="tablist" aria-label="Filter case outcomes">
          {(
            [
              ["all", "All"],
              ["fixed", "Fixed"],
              ["steady", "Steady"],
              ["regress", "Regressed"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={filter === id}
              className={filter === id ? "active" : ""}
              onClick={() => setFilter(id)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <ul className="eval-case-grid">
        {filtered.map((item) => (
          <li key={item.id} className={`eval-case-card ${item.change}`}>
            <div className="eval-case-top">
              <span className="eval-cat-pill">{item.meta.category}</span>
              <span className={`eval-change-pill ${item.change}`}>
                {item.change === "fixed"
                  ? "Fail → Pass"
                  : item.change === "steady"
                    ? "Pass → Pass"
                    : item.change === "regress"
                      ? "Pass → Fail"
                      : "Fail → Fail"}
              </span>
            </div>
            <strong>{item.meta.title}</strong>
            <p>{item.meta.blurb}</p>
            <div className="eval-outcome-track" aria-hidden="true">
              <span className={item.baselinePass ? "ok" : "bad"}>Baseline</span>
              <span className="arrow">→</span>
              <span className={item.improvedPass ? "ok" : "bad"}>Improved</span>
            </div>
            {item.notes && item.notes !== "pass" && <small>{item.notes}</small>}
          </li>
        ))}
        {!filtered.length && <li className="fy-empty">No cases in this filter.</li>}
      </ul>

      <details className="eval-method">
        <summary>Scoring logic (what “pass” means)</summary>
        <ul>
          <li>
            <strong>Lookup / absence</strong> — answer must include expected source figures or clearly state missing
            information; inventing values fails.
          </li>
          <li>
            <strong>Calculation</strong> — must produce a system-calculated payload (not an LLM guess), with expected
            totals where defined.
          </li>
          <li>
            <strong>Financial year</strong> — Indian FY Apr–Mar filtering, coverage language, and no silent cross-org
            merges.
          </li>
          <li>
            <strong>Safety</strong> — refuse blind combined totals across different organisations.
          </li>
        </ul>
        <p>
          Baseline packages the pre-calculator refusals. Improved runs the same cases through `calculations.py`. Live
          OpenAI lookup quality is separate from this offline scorecard.
        </p>
      </details>
    </section>
  );
}
