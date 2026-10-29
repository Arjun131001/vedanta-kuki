import { useEffect, useMemo, useState } from "react";
import Select from "./Select";

type Doc = { id: string; filename: string; status: string };
type FySummary = {
  year: number;
  bounds: [string, string];
  coverage: string;
  totals: { unit: string; value: string; operand_count: number }[];
  items: {
    value: string;
    unit?: string;
    filename?: string;
    period_start?: string | null;
    period_end?: string | null;
    label?: string;
    citation_id?: string;
  }[];
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
          Indian financial years run April–March. Totals are system-calculated from reported source values and stay
          distinct from document-reported figures.
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
              summary.totals.map((total) => (
                <article key={total.unit}>
                  <small>Calculated total</small>
                  <strong>
                    {total.value} {total.unit}
                  </strong>
                  <span>{total.operand_count} reported values</span>
                </article>
              ))
            ) : (
              <p className="fy-empty">No same-unit totals could be calculated for this year.</p>
            )}
          </div>
          <div className="fy-items">
            <h3>Included evidence</h3>
            {summary.items.length ? (
              <ul>
                {summary.items.map((item, index) => (
                  <li key={`${item.citation_id || item.label}-${index}`}>
                    <button type="button" onClick={() => item.filename && ready.find((d) => d.filename === item.filename) && onOpenSource(ready.find((d) => d.filename === item.filename)!.id)}>
                      <strong>
                        {item.value}
                        {item.unit ? ` ${item.unit}` : ""}
                      </strong>
                      <span>{item.filename}</span>
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

export function EvalComparisonPanel() {
  const [data, setData] = useState<{
    available: boolean;
    message?: string;
    baseline: { overall?: { score?: number; passed?: number; total?: number }; cases?: { id: string; pass: boolean; notes?: string }[] } | null;
    improved: { overall?: { score?: number; passed?: number; total?: number }; cases?: { id: string; pass: boolean; notes?: string }[] } | null;
  } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void fetch(`${api}/api/eval/comparison`)
      .then(async (response) => {
        if (!response.ok) throw Error("Could not load evaluation comparison.");
        setData(await response.json());
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load evaluation comparison."));
  }, []);

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
  const cases = data.improved?.cases || [];

  return (
    <section className="eval-panel">
      <div className="section-kicker">EVALUATION</div>
      <h2>Baseline vs improved</h2>
      <div className="eval-scores">
        <article>
          <small>Baseline</small>
          <strong>
            {baseline?.passed ?? 0}/{baseline?.total ?? 0}
          </strong>
          <span>{baseline?.score ?? 0}% passed</span>
        </article>
        <article className="improved">
          <small>Improved</small>
          <strong>
            {improved?.passed ?? 0}/{improved?.total ?? 0}
          </strong>
          <span>{improved?.score ?? 0}% passed</span>
        </article>
      </div>
      <ul className="eval-cases">
        {cases.map((item) => {
          const before = data.baseline?.cases?.find((c) => c.id === item.id);
          return (
            <li key={item.id} className={item.pass ? "pass" : "fail"}>
              <strong>{item.id}</strong>
              <span>
                {before?.pass ? "pass" : "fail"} → {item.pass ? "pass" : "fail"}
              </span>
              {item.notes && <small>{item.notes}</small>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
