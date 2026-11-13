import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRightLeft,
  BarChart3,
  Check,
  Copy,
  Download,
  Info,
  Loader2,
  Play,
  Sparkles,
  Table2,
  User,
  Wrench,
} from "lucide-react";
import { inferChart } from "../lib/chart";
import { downloadText, formatDuration, toCsv } from "../lib/format";
import type { Schema, Theme, Turn } from "../types";
import { ResultChart } from "./ResultChart";
import { ResultsTable } from "./ResultsTable";
import { SqlEditor } from "./SqlEditor";

interface Props {
  turn: Turn;
  schema: Schema | null;
  dialect: string;
  theme: Theme;
  onRun: (turn: Turn, sql: string) => void;
  dbName: (id: string) => string;
  onSwitchDb: (turn: Turn) => void;
}

export function TurnCard({ turn, schema, dialect, theme, onRun, dbName, onSwitchDb }: Props) {
  const [sql, setSql] = useState(turn.sql);
  const [view, setView] = useState<"table" | "chart">("table");
  const [copied, setCopied] = useState(false);
  const [showAttempts, setShowAttempts] = useState(false);

  // Take the SQL from the server when it arrives, but don't overwrite the user's text
  // when the server only normalised it (e.g. stripped a trailing semicolon).
  useEffect(() => {
    const norm = (s: string) => s.trim().replace(/;+$/, "").trim();
    setSql((current) => (norm(current) === norm(turn.sql) ? current : turn.sql));
  }, [turn.sql]);

  const chart = useMemo(() => (turn.result ? inferChart(turn.result) : null), [turn.result]);
  useEffect(() => {
    if (!chart) setView("table");
  }, [chart]);

  const busy = turn.status !== "done";
  const edited = sql.trim() !== turn.sql.trim();

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked */
    }
  };

  const run = () => {
    if (sql.trim() && !busy) onRun(turn, sql);
  };

  return (
    <article className="turn">
      {turn.question && (
        <div className="turn-question">
          <div className="avatar user" aria-hidden>
            <User size={14} />
          </div>
          <p>{turn.question}</p>
        </div>
      )}

      <div className="turn-answer">
        <div className="avatar ai" aria-hidden>
          {turn.mode === "ai" ? <Sparkles size={14} /> : <Table2 size={14} />}
        </div>
        <div className="turn-body">
          {turn.status === "thinking" && (
            <div className="thinking">
              <Loader2 size={16} className="spin" /> Writing SQL and running it…
            </div>
          )}

          {turn.status !== "thinking" && turn.answerable === false && (
            <div className="notice info">
              <Info size={16} />
              <div>
                <strong>This question can't be answered from this database.</strong>
                {turn.explanation && <p>{turn.explanation}</p>}
              </div>
            </div>
          )}

          {turn.status !== "thinking" && turn.answerable !== false && (
            <>
              {turn.routedFrom && turn.queryDb && (
                <div className="notice routed">
                  <ArrowRightLeft size={15} />
                  <span>
                    Answered from <strong>{dbName(turn.queryDb)}</strong>, because {dbName(turn.routedFrom)} doesn't have
                    this data.
                  </span>
                  <button className="ghost-btn" onClick={() => onSwitchDb(turn)}>
                    Switch to {dbName(turn.queryDb)}
                  </button>
                </div>
              )}
              {turn.explanation && <p className="explanation">{turn.explanation}</p>}

              {(turn.sql || turn.mode === "sql") && (
                <div className="sql-block">
                  <div className="sql-block-header">
                    <span className="label">SQL{edited ? " (edited)" : ""}</span>
                    <div className="actions">
                      <button className="ghost-btn" onClick={copy} title="Copy SQL">
                        {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? "Copied" : "Copy"}
                      </button>
                      <button className="primary-btn small" onClick={run} disabled={busy || !sql.trim()} title="Run (Ctrl+Enter)">
                        {turn.status === "running" ? <Loader2 size={14} className="spin" /> : <Play size={14} />} Run
                      </button>
                    </div>
                  </div>
                  <SqlEditor value={sql} onChange={setSql} onRun={run} dialect={dialect} schema={schema} theme={theme} />
                </div>
              )}

              {turn.attempts && turn.attempts.length > 0 && (
                <div className="notice subtle">
                  <Wrench size={14} />
                  <div>
                    <button className="link-btn" onClick={() => setShowAttempts((s) => !s)}>
                      Fixed {turn.attempts.length} error{turn.attempts.length > 1 ? "s" : ""} automatically
                      {showAttempts ? " (hide)" : " (show)"}
                    </button>
                    {showAttempts &&
                      turn.attempts.map((a, i) => (
                        <div key={i} className="attempt">
                          <pre>{a.sql}</pre>
                          <span className="error-text">{a.error}</span>
                        </div>
                      ))}
                  </div>
                </div>
              )}

              {turn.error && (
                <div className="notice error" role="alert">
                  <AlertTriangle size={16} />
                  <div>
                    <strong>{turn.result === undefined && !turn.sql ? "Something went wrong" : "The query failed"}</strong>
                    <p>{turn.error}</p>
                  </div>
                </div>
              )}

              {turn.result && (
                <div className={"result" + (turn.status === "running" ? " stale" : "")}>
                  <div className="result-toolbar">
                    <div className="segmented small" role="tablist" aria-label="Result view">
                      <button role="tab" aria-selected={view === "table"} className={view === "table" ? "active" : ""} onClick={() => setView("table")}>
                        <Table2 size={14} /> Table
                      </button>
                      <button
                        role="tab"
                        aria-selected={view === "chart"}
                        className={view === "chart" ? "active" : ""}
                        onClick={() => setView("chart")}
                        disabled={!chart}
                        title={chart ? "Show as chart" : "This result has no numeric column to chart"}
                      >
                        <BarChart3 size={14} /> Chart
                      </button>
                    </div>
                    <span className="meta">
                      {turn.result.row_count.toLocaleString()} row{turn.result.row_count === 1 ? "" : "s"}
                      {turn.result.truncated && " (limit reached)"} · {formatDuration(turn.result.elapsed_ms)}
                    </span>
                    <button
                      className="ghost-btn"
                      onClick={() => downloadText(`query-${turn.id.slice(0, 8)}.csv`, toCsv(turn.result!))}
                      disabled={turn.result.row_count === 0}
                      title="Download as CSV"
                    >
                      <Download size={14} /> CSV
                    </button>
                  </div>
                  {turn.result.truncated && (
                    <p className="hint">
                      Only the first {turn.result.row_count.toLocaleString()} rows are shown. Add filters or a LIMIT to narrow
                      the result.
                    </p>
                  )}
                  {view === "chart" && chart ? (
                    <ResultChart key={turn.result.elapsed_ms} spec={chart} theme={theme} />
                  ) : (
                    <ResultsTable result={turn.result} />
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </article>
  );
}
