import { useCallback, useEffect, useRef, useState } from "react";
import "./chat.css";
import { parseAnswer, parseInline } from "./answer.mjs";

type Doc = { id: string; filename: string; status: string };
type Citation = {
  id: string;
  document_id: string;
  filename: string;
  unit_index: number;
  unit_label: string;
  reference_id: string;
  quote: string;
  cells: string[];
  evidence_status: string;
};
type Calculation = {
  operation: string;
  unit?: string;
  result?: string;
  kind?: string;
  operands?: { value: string; unit?: string; filename?: string; label?: string }[];
};
type Turn = {
  id: string;
  question: string;
  status: "queued" | "processing" | "ready" | "failed";
  answer: string | null;
  citations: Citation[];
  limitations: string[];
  calculations?: Calculation[];
  error: string | null;
};
type Session = {
  id: string;
  title: string;
  document_ids: string[];
  created_at: number;
  updated_at: number;
  messages: Turn[];
};

const api = import.meta.env.VITE_API_URL || "";
const evidenceLabel = (status: string) =>
  (
    {
      source_text_unreviewed: "Source text · unreviewed",
      needs_review: "Needs review",
      source_checked: "Source checks passed",
    } as Record<string, string>
  )[status] || "Source evidence";

const suggestions = [
  "What electricity consumption does each bill report, and for which period?",
  "What is the total waste quantity recorded? Calculate the sum.",
  "What is the total for financial year 2024?",
];

function isCalcQuestion(question: string) {
  return (
    /\b(calculate|compute|sum|add up|difference|subtract|aggregate|year.over.year|year.on.year|percent(?:age)? change|how much more|how much less)\b/i.test(
      question,
    ) ||
    (/\b(?:fy\s*\d*|financial year|fiscal year)\b/i.test(question) &&
      /\b(?:total|combined|across)\b/i.test(question))
  );
}

function AnswerContent({
  text,
  citations,
  onCitation,
}: {
  text: string;
  citations: Citation[];
  onCitation: (id: string, unit: number) => void;
}) {
  const inline = (value: string) =>
    parseInline(value, citations.length).map((part, i) => {
    if (part.type === "bold") return <strong key={i}>{part.text}</strong>;
      if (part.type === "citation") {
        const citation = citations[part.index - 1];
        return (
          <button
            key={i}
            className="inline-citation"
            aria-label={`Open source ${part.index}: ${citation.filename}, ${citation.unit_label}`}
            onClick={() => onCitation(citation.document_id, citation.unit_index)}
          >
            {part.text}
          </button>
        );
      }
    return part.text;
  });
  return (
    <div className="chat-answer-text">
      {parseAnswer(text).map((block, i) => {
    if (block.type === "heading") return <h3 key={i}>{inline(block.text)}</h3>;
    if (block.type === "paragraph") return <p key={i}>{inline(block.text)}</p>;
    const items = block.items.map((item, n) => <li key={n}>{inline(item)}</li>);
    return block.type === "ordered" ? <ol key={i}>{items}</ol> : <ul key={i}>{items}</ul>;
      })}
    </div>
  );
}

export default function ChatWorkspace({
  docs,
  online,
  active,
  onCitation,
}: {
  docs: Doc[];
  online: boolean;
  active: boolean;
  onCitation: (id: string, unit: number) => void;
}) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [session, setSession] = useState<Session | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState("");
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [pending, setPending] = useState(false);
  const [loadingSession, setLoadingSession] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState("");
  const [railOpen, setRailOpen] = useState(false);
  const [nearBottom, setNearBottom] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const request = useRef<{ question: string; key: string; id: string } | null>(null);
  const sessionRef = useRef<string | null>(null);
  const loadController = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      loadController.current?.abort();
      sessionRef.current = null;
    },
    [],
  );

  const list = useCallback(async () => {
    try {
      const r = await fetch(`${api}/api/qa/sessions`);
      if (!r.ok) throw Error();
      const d = await r.json();
      setSessions(d.sessions);
    } catch {
      if (online) setError("Could not load conversations.");
    }
  }, [online]);

  useEffect(() => {
    if (!active || !online) return;
    void list();
    const controller = new AbortController();
    fetch(`${api}/api/facts/config`, { signal: controller.signal })
      .then((r) => {
        if (!r.ok) throw Error();
        return r.json();
      })
      .then((d) => setConfigured(Boolean(d.configured)))
      .catch(() => {
        if (!controller.signal.aborted) setConfigured(false);
      });
    return () => controller.abort();
  }, [active, online, list]);

  const load = useCallback(async (id: string, signal?: AbortSignal) => {
    const r = await fetch(`${api}/api/qa/sessions/${encodeURIComponent(id)}`, { signal });
    if (!r.ok) throw Error("Could not load this conversation.");
    const d: Session = await r.json();
    if (sessionRef.current === id && !signal?.aborted) {
      setSession(d);
      setSelected(d.document_ids);
    }
  }, []);

  function openSession(id: string) {
    if (pending) return;
    loadController.current?.abort();
    const c = new AbortController();
    loadController.current = c;
    sessionRef.current = id;
    setSession(null);
    setSelected([]);
    setDraft("");
    request.current = null;
    setLoadingSession(true);
    setError("");
    setRailOpen(false);
    void load(id, c.signal)
      .catch((e) => {
        if (!c.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!c.signal.aborted) setLoadingSession(false);
      });
  }

  useEffect(() => {
    if (!active || !session || !session.messages.some((m) => m.status === "queued" || m.status === "processing")) return;
    const c = new AbortController();
    const timer = setInterval(() => {
      void load(session.id, c.signal)
        .then(() => list())
        .catch(() => {});
    }, 2000);
    return () => {
      c.abort();
      clearInterval(timer);
    };
  }, [active, session, load, list]);

  function newChat() {
    if (pending) return;
    loadController.current?.abort();
    setLoadingSession(false);
    sessionRef.current = null;
    setSession(null);
    setSelected([]);
    setDraft("");
    setError("");
    request.current = null;
    setRailOpen(false);
  }

  async function send() {
    const question = draft.trim();
    const calcQuestion = isCalcQuestion(question);
    if (
      !question ||
      question.length > 4000 ||
      !selected.length ||
      pending ||
      loadingSession ||
      !online ||
      (!configured && !calcQuestion) ||
      session?.messages.some((m) => m.status === "queued" || m.status === "processing")
    ) {
      return;
    }
    setPending(true);
    setError("");
    const key = `${session?.id || "new"}:${selected.slice().sort().join(",")}`;
    const attempt =
      request.current?.question === question && request.current.key === key
        ? request.current
        : { question, key, id: crypto.randomUUID() };
    request.current = attempt;
    try {
      let id = session?.id;
      if (!id) {
        const r = await fetch(`${api}/api/qa/sessions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ document_ids: selected }),
        });
        if (!r.ok) throw Error("Could not create a conversation.");
        const created: Session = await r.json();
        id = created.id;
        sessionRef.current = id;
        setSession(created);
        attempt.key = `${id}:${created.document_ids.slice().sort().join(",")}`;
        await list();
      }
      const r = await fetch(`${api}/api/qa/sessions/${encodeURIComponent(id)}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, request_id: attempt.id }),
      });
      if (!r.ok) {
        let detail = "Could not send your question. Please try again.";
        try {
          const body = await r.json();
          if (typeof body.detail === "string") detail = body.detail;
        } catch {
          /* ignore */
        }
        throw Error(detail);
      }
      request.current = null;
      setDraft("");
      await load(id);
      await list();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setPending(false);
    }
  }

  const working = pending || Boolean(session?.messages.some((m) => m.status === "queued" || m.status === "processing"));
  useEffect(() => {
    const el = scrollRef.current;
    if (el && nearBottom) el.scrollTop = el.scrollHeight;
  }, [session, nearBottom]);

  const names = (session?.document_ids || selected).map((id) => docs.find((d) => d.id === id)?.filename || id);
  const canSend =
    Boolean(draft.trim()) &&
    selected.length > 0 &&
    !working &&
    !loadingSession &&
    !(sessionRef.current && !session) &&
    online &&
    !(configured === false && !isCalcQuestion(draft));

  return (
    <div className="chat-workspace">
      <button
        className={`chat-rail-backdrop ${railOpen ? "open" : ""}`}
        aria-label="Close history"
        onClick={() => setRailOpen(false)}
      />
      <aside className={`chat-rail ${railOpen ? "open" : ""}`} aria-label="Conversation history">
        <button className="chat-new" disabled={pending} onClick={newChat}>
          ＋ New chat
        </button>
        <div className="chat-rail-label">Chats</div>
        {sessions.length ? (
          sessions.map((s) => (
            <button
              key={s.id}
              className={`chat-session ${session?.id === s.id ? "current" : ""}`}
              disabled={pending}
              onClick={() => openSession(s.id)}
            >
              {s.title || "New conversation"}
            </button>
          ))
        ) : (
          <p className="chat-muted">No chats yet.</p>
        )}
      </aside>

      <section className="chat-main">
        <div className="chat-top">
          <button className="chat-rail-toggle" onClick={() => setRailOpen(!railOpen)} aria-expanded={railOpen} aria-label="Open chats">
            ☰
          </button>
          <h1>Verdant</h1>
          <div className="chat-top-actions">
            <button className="chat-icon-btn" disabled={pending} onClick={newChat} aria-label="New chat">
              ＋
            </button>
          </div>
        </div>

        <div
          className="chat-scroll"
          ref={scrollRef}
          onScroll={(e) => {
            const el = e.currentTarget;
            setNearBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 100);
          }}
        >
          {loadingSession && (
            <p className="chat-working">
              <span className="chat-pulse" aria-hidden="true">
                <i></i>
                <i></i>
                <i></i>
              </span>
              Loading…
            </p>
          )}

          {!loadingSession && !sessionRef.current && !session?.messages.length && (
            <div className="chat-welcome">
              <div className="chat-welcome-inner">
                <div className="chat-spark" aria-hidden="true">
                  ✦
                </div>
                <h2>What can I help with?</h2>
                <p>Choose documents below, then ask a question.</p>
                <div className="chat-suggestions">
                  {suggestions.map((text) => (
                    <button key={text} onClick={() => setDraft(text)}>
                      {text}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {session?.messages.map((m) => (
            <div className="chat-turn" key={m.id}>
              <div className="chat-user">{m.question}</div>
              <div className="chat-answer">
                <div className="chat-answer-label" aria-hidden="true">
                  ✦
                </div>
                <div className="chat-answer-body">
                  {m.status === "queued" || m.status === "processing" ? (
                    <p className="chat-working" role="status">
                      <span className="chat-pulse" aria-hidden="true">
                        <i></i>
                        <i></i>
                        <i></i>
                      </span>
                      {m.status === "queued" ? "Queued" : "Thinking"}…
                    </p>
                  ) : m.status === "failed" ? (
                    <div className="chat-failed">
                      <p>{m.error || "This question could not be answered."}</p>
                      <button
                        onClick={() => {
                          setDraft(m.question);
                          request.current = null;
                        }}
                      >
                        Ask again
                      </button>
                    </div>
                  ) : (
                    <>
                      <AnswerContent
                        text={m.answer?.trim() || "I can’t provide a supported answer to this question yet."}
                        citations={m.citations || []}
                        onCitation={onCitation}
                      />
                      {(m.calculations?.length || 0) > 0 && (
                        <div className="chat-calc">
                          <strong>Calculations</strong>
                          {m.calculations!.map((calc, i) => (
                            <p key={i}>
                              <span className="chat-calc-result">
                                {calc.result}
                                {calc.unit ? ` ${calc.unit}` : ""}
                              </span>{" "}
                              · {calc.operation.split("_").join(" ")}
                              {calc.kind === "calculated" ? " · system-calculated" : ""}
                            </p>
                          ))}
                        </div>
                      )}
                      {m.limitations?.length > 0 && (
                        <details className="chat-limitations">
                          <summary>
                            Limitations ({m.limitations.length}) <span>· review needed</span>
                          </summary>
                          {m.limitations.map((x, i) => (
                            <p key={i}>{x}</p>
                          ))}
                        </details>
                      )}
                      {m.citations?.length > 0 && (
                        <details className="chat-citations">
                          <summary>Sources ({m.citations.length})</summary>
                          <div>
                            {m.citations.map((c, index) => (
                              <button key={c.id} onClick={() => onCitation(c.document_id, c.unit_index)}>
                                <span className="citation-title">
                                  [{index + 1}] {c.filename} <span>↗</span>
                                </span>
                                <small>
                                  {c.unit_label} · {evidenceLabel(c.evidence_status)}
                                </small>
                                {c.quote && <span className="citation-quote">“{c.quote}”</span>}
                                {c.cells?.length > 0 && <small>{c.cells.join(", ")}</small>}
                              </button>
                            ))}
                          </div>
                        </details>
                      )}
                      <button
                        className="chat-copy"
                        onClick={() => {
                          void navigator.clipboard
                            .writeText(m.answer || "")
                            .then(() => {
                              setCopied(m.id);
                              setTimeout(() => setCopied(""), 2000);
                            })
                            .catch(() => setError("Could not copy the answer."));
                        }}
                      >
                        {copied === m.id ? "Copied" : "Copy"}
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="chat-compose">
          <div className="chat-compose-inner">
          {!nearBottom && (
            <button
              className="chat-jump"
              onClick={() => {
                const el = scrollRef.current;
                if (el) el.scrollTop = el.scrollHeight;
                setNearBottom(true);
              }}
            >
              ↓ Jump to latest
            </button>
          )}
          <div className="chat-compose-shell">
            <div className="chat-scope">
              <details className="chat-source-menu">
                <summary>
                  {names.length ? `${names.length} document${names.length === 1 ? "" : "s"} selected` : "Choose documents"}
                  {session ? " · locked" : ""}
                </summary>
                <div className="chat-picker">
                  <strong>{session ? "Documents in this chat" : "Choose up to 10 documents"}</strong>
                  {!session && !loadingSession && !sessionRef.current && !pending && (
                    <input
                      aria-label="Search documents"
                      placeholder="Search documents"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  )}
                  {session ? (
                    names.map((name, i) => (
                      <p className="chat-selected-source" key={i}>
                        ✓ {name}
                      </p>
                    ))
                  ) : (
                    docs
                      .filter((d) => d.status === "ready" && d.filename.toLowerCase().includes(search.toLowerCase()))
                      .map((d) => (
                        <label key={d.id}>
                          <input
                            type="checkbox"
                            aria-label={`Include ${d.filename}`}
                            checked={selected.includes(d.id)}
                            disabled={
                              loadingSession ||
                              pending ||
                              !!sessionRef.current ||
                              (!selected.includes(d.id) && selected.length >= 10)
                            }
                            onChange={() =>
                              setSelected(
                                selected.includes(d.id) ? selected.filter((x) => x !== d.id) : [...selected, d.id],
                              )
                            }
                          />
                          <span>{d.filename}</span>
                        </label>
                      ))
                  )}
                  {!session && !docs.some((d) => d.status === "ready") && (
                    <p>No extracted documents yet. Add files in the library first.</p>
                  )}
                </div>
              </details>
              {!session && names.length > 0 && (
                <div className="chat-selected-chips">
                  {names.slice(0, 2).map((name) => (
                    <span key={name} title={name}>
                      {name}
                    </span>
                  ))}
                  {names.length > 2 && <span>+{names.length - 2}</span>}
                </div>
              )}
            </div>

            {error && (
              <p className="chat-error" role="alert">
                {error}
              </p>
            )}
            {configured === false && (
              <p className="chat-error">
                Model not configured for lookups. Calculation and financial-year questions still work locally.
              </p>
            )}

            <div className="chat-input">
              <textarea
                disabled={loadingSession || pending || (!!sessionRef.current && !session)}
                aria-label="Your question"
                placeholder="Ask anything about your documents…"
                value={draft}
                maxLength={4000}
                rows={1}
                onChange={(e) => {
                  setDraft(e.target.value);
                  if (request.current?.question !== e.target.value.trim()) request.current = null;
                  const el = e.currentTarget;
                  el.style.height = "auto";
                  el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send();
                  }
                }}
              />
              <button onClick={() => void send()} disabled={!canSend} aria-label={pending ? "Sending" : "Send"}>
                {pending ? <span className="chat-spinner" aria-hidden="true" /> : "↑"}
              </button>
            </div>
          </div>
          <p className="chat-disclosure">
            Lookups use OpenAI. Calculations and financial-year totals stay local.
          </p>
          </div>
        </div>
      </section>
      </div>
  );
}
