import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Database,
  History as HistoryIcon,
  Menu,
  MessageSquarePlus,
  Moon,
  RefreshCw,
  Sun,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { api, errorMessage } from "./api";
import { Composer } from "./components/Composer";
import { HistoryPanel } from "./components/HistoryPanel";
import { SchemaPanel } from "./components/SchemaPanel";
import { TurnCard } from "./components/TurnCard";
import { UploadDialog } from "./components/UploadDialog";
import { newId } from "./lib/format";
import { load, save } from "./lib/storage";
import type { DatabaseInfo, Health, HistoryItem, HistoryTurn, Schema, Theme, Turn } from "./types";

const MAX_CONTEXT_TURNS = 4;

function initialTheme(): Theme {
  const saved = load("theme");
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [health, setHealth] = useState<Health | null>(null);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [databases, setDatabases] = useState<DatabaseInfo[]>([]);
  const [dbId, setDbId] = useState<string | null>(() => load("database"));
  const [schema, setSchema] = useState<Schema | null>(null);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [schemaError, setSchemaError] = useState<string | null>(null);
  const [examples, setExamples] = useState<string[]>([]);
  const [turnsByDb, setTurnsByDb] = useState<Record<string, Turn[]>>({});
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [tab, setTab] = useState<"schema" | "history">("schema");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [mode, setMode] = useState<"ai" | "sql">("ai");
  const [question, setQuestion] = useState("");
  const [sqlDraft, setSqlDraft] = useState("");
  const [composerKey, setComposerKey] = useState(0);
  const [toast, setToast] = useState<{ text: string; kind: "ok" | "error" } | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const db = databases.find((d) => d.id === dbId) ?? null;
  const turns = useMemo(() => (dbId ? turnsByDb[dbId] ?? [] : []), [turnsByDb, dbId]);
  const busy = turns.some((t) => t.status === "thinking");
  const llmEnabled = !!health?.llm_enabled;
  const aiName = health?.provider === "groq" ? "Groq" : health?.provider === "anthropic" ? "Claude" : "AI";

  // ---------- theme ----------
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    save("theme", theme);
  }, [theme]);

  // ---------- toast ----------
  const notify = useCallback((text: string, kind: "ok" | "error" = "ok") => {
    setToast({ text, kind });
    window.setTimeout(() => setToast((t) => (t?.text === text ? null : t)), 4000);
  }, []);

  // ---------- initial load ----------
  const loadDatabases = useCallback(async () => {
    try {
      const [h, dbs] = await Promise.all([api.health(), api.databases()]);
      setHealth(h);
      setDatabases(dbs);
      setConnectError(null);
      if (!h.llm_enabled) setMode("sql");
      return dbs;
    } catch (e) {
      setConnectError(errorMessage(e));
      return [];
    }
  }, []);

  useEffect(() => {
    loadDatabases();
  }, [loadDatabases]);

  // Pick a valid database once the list is known.
  useEffect(() => {
    if (databases.length && !databases.some((d) => d.id === dbId)) setDbId(databases[0].id);
  }, [databases, dbId]);

  useEffect(() => {
    if (dbId) save("database", dbId);
  }, [dbId]);

  const refreshHistory = useCallback(async () => {
    if (!dbId) return;
    try {
      setHistory(await api.history(dbId));
    } catch {
      /* history is non-essential */
    }
  }, [dbId]);

  // Load schema, examples and history whenever the database changes.
  useEffect(() => {
    if (!dbId || !databases.some((d) => d.id === dbId)) return;
    let cancelled = false;
    setSchema(null);
    setSchemaError(null);
    setSchemaLoading(true);
    setExamples([]);
    api
      .schema(dbId)
      .then((s) => !cancelled && setSchema(s))
      .catch((e) => !cancelled && setSchemaError(errorMessage(e)))
      .finally(() => !cancelled && setSchemaLoading(false));
    api
      .examples(dbId)
      .then((ex) => !cancelled && setExamples(ex))
      .catch(() => {});
    refreshHistory();
    return () => {
      cancelled = true;
    };
  }, [dbId, databases, refreshHistory]);

  // Scroll to the newest turn when it's added and again when its answer arrives.
  const lastStatus = turns.at(-1)?.status;
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, lastStatus]);

  // ---------- turns ----------
  const addTurn = (turn: Turn) =>
    setTurnsByDb((all) => ({ ...all, [turn.databaseId]: [...(all[turn.databaseId] ?? []), turn] }));

  const patchTurn = (databaseId: string, id: string, patch: Partial<Turn>) =>
    setTurnsByDb((all) => ({
      ...all,
      [databaseId]: (all[databaseId] ?? []).map((t) => (t.id === id ? { ...t, ...patch } : t)),
    }));

  const ask = async (text: string) => {
    if (!dbId || !text.trim()) return;
    const context: HistoryTurn[] = turns
      .filter((t) => t.status === "done" && t.sql && !t.error && !t.routedFrom)
      .slice(-MAX_CONTEXT_TURNS)
      .map((t) => ({ question: t.question ?? "(query written by the user)", sql: t.sql }));
    const turn: Turn = { id: newId(), databaseId: dbId, mode: "ai", question: text.trim(), sql: "", status: "thinking" };
    addTurn(turn);
    setQuestion("");
    try {
      const r = await api.generate({ database_id: dbId, question: turn.question!, history: context });
      patchTurn(dbId, turn.id, {
        status: "done",
        sql: r.sql,
        explanation: r.explanation,
        answerable: r.answerable,
        result: r.result,
        error: r.error,
        attempts: r.attempts,
        historyId: r.history_id,
        queryDb: r.database_id,
        routedFrom: r.routed_from,
      });
    } catch (e) {
      patchTurn(dbId, turn.id, { status: "done", error: errorMessage(e) });
    }
    refreshHistory();
  };

  // Move an answer that came from another database into that database's conversation and switch to it.
  const switchToAnswerDb = (turn: Turn) => {
    const target = turn.queryDb;
    if (!target || target === turn.databaseId) return;
    setTurnsByDb((all) => ({
      ...all,
      [turn.databaseId]: (all[turn.databaseId] ?? []).filter((t) => t.id !== turn.id),
      [target]: [...(all[target] ?? []), { ...turn, databaseId: target, routedFrom: null }],
    }));
    setDbId(target);
  };

  const dbName = (id: string) => databases.find((d) => d.id === id)?.name ?? id;

  const runSql = async (sql: string, label?: string) => {
    if (!dbId || !sql.trim()) return;
    const turn: Turn = { id: newId(), databaseId: dbId, mode: "sql", question: label, sql: sql.trim(), status: "running" };
    addTurn(turn);
    try {
      const r = await api.execute({ database_id: dbId, sql, question: label });
      patchTurn(dbId, turn.id, { status: "done", sql: r.sql, result: r.result, error: r.error, historyId: r.history_id });
    } catch (e) {
      patchTurn(dbId, turn.id, { status: "done", error: errorMessage(e) });
    }
    refreshHistory();
  };

  const rerun = async (turn: Turn, sql: string) => {
    patchTurn(turn.databaseId, turn.id, { status: "running" });
    try {
      const r = await api.execute({ database_id: turn.queryDb ?? turn.databaseId, sql, question: turn.question });
      patchTurn(turn.databaseId, turn.id, {
        status: "done",
        sql: r.sql,
        result: r.result ?? turn.result,
        error: r.error,
        answerable: true,
        attempts: [],
      });
    } catch (e) {
      patchTurn(turn.databaseId, turn.id, { status: "done", error: errorMessage(e) });
    }
    refreshHistory();
  };

  const submit = () => {
    if (mode === "ai") ask(question);
    else {
      runSql(sqlDraft);
      setSqlDraft("");
      setComposerKey((k) => k + 1);
    }
  };

  const newConversation = () => dbId && setTurnsByDb((all) => ({ ...all, [dbId]: [] }));

  // ---------- history actions ----------
  const openHistory = (item: HistoryItem) => {
    setSidebarOpen(false);
    runSql(item.sql, item.question ?? undefined);
  };
  const starHistory = async (item: HistoryItem) => {
    try {
      const updated = await api.starHistory(item.id, !item.starred);
      setHistory((h) => h.map((i) => (i.id === item.id ? updated : i)));
    } catch (e) {
      notify(errorMessage(e), "error");
    }
  };
  const deleteHistory = async (item: HistoryItem) => {
    try {
      await api.deleteHistory(item.id);
      setHistory((h) => h.filter((i) => i.id !== item.id));
    } catch (e) {
      notify(errorMessage(e), "error");
    }
  };
  const clearHistory = async () => {
    if (!dbId) return;
    try {
      await api.clearHistory(dbId);
      refreshHistory();
    } catch (e) {
      notify(errorMessage(e), "error");
    }
  };

  // ---------- databases ----------
  const onUploaded = async (info: DatabaseInfo) => {
    setUploadOpen(false);
    await loadDatabases();
    setDbId(info.id);
    // re-read the schema even if the same database was selected (a table may have been added)
    if (info.id === dbId) {
      setSchemaLoading(true);
      api.schema(info.id).then(setSchema).finally(() => setSchemaLoading(false));
    }
    notify(`“${info.name}” is ready. Ask it a question!`);
  };

  const deleteDatabase = async () => {
    if (!db?.deletable) return;
    if (!confirm(`Delete the uploaded database “${db.name}”? This can't be undone.`)) return;
    try {
      await api.deleteDatabase(db.id);
      setTurnsByDb(({ [db.id]: _removed, ...rest }) => rest);
      await loadDatabases();
      notify(`Deleted “${db.name}”.`);
    } catch (e) {
      notify(errorMessage(e), "error");
    }
  };

  const previewTable = (table: string) => {
    setSidebarOpen(false);
    const quoted = /^[a-z_][a-z0-9_]*$/i.test(table) ? table : `"${table.replace(/"/g, '""')}"`;
    runSql(`SELECT * FROM ${quoted} LIMIT 50`, `Preview of ${table}`);
  };

  // ---------- render ----------
  if (connectError && !health) {
    return (
      <div className="fatal">
        <Database size={32} />
        <h1>Can't connect to the server</h1>
        <p>{connectError}</p>
        <p className="muted">
          Start the backend with <code>python -m app</code> in the <code>backend</code> folder, then try again.
        </p>
        <button className="primary-btn" onClick={loadDatabases}>
          <RefreshCw size={14} /> Retry
        </button>
      </div>
    );
  }

  const uploaded = databases.filter((d) => d.kind === "upload");

  return (
    <div className="app">
      <header className="topbar">
        <button className="icon-btn mobile-only" onClick={() => setSidebarOpen((o) => !o)} aria-label="Toggle sidebar">
          {sidebarOpen ? <X size={18} /> : <Menu size={18} />}
        </button>
        <div className="brand">
          <img src="/favicon.svg" alt="" width={26} height={26} />
          <span>Text-to-SQL</span>
        </div>

        <div className="db-picker">
          <Database size={15} className="muted" />
          <select value={dbId ?? ""} onChange={(e) => setDbId(e.target.value)} aria-label="Database">
            {databases.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
                {d.kind === "upload" ? " (uploaded)" : d.kind === "external" ? ` (${d.dialect})` : ""}
              </option>
            ))}
          </select>
          {db?.deletable && (
            <button className="icon-btn" onClick={deleteDatabase} title="Delete this uploaded database">
              <Trash2 size={15} />
            </button>
          )}
        </div>

        <div className="topbar-actions">
          <button className="ghost-btn" onClick={() => setUploadOpen(true)}>
            <Upload size={15} /> <span className="hide-sm">Upload data</span>
          </button>
          <span
            className={"status-pill " + (llmEnabled ? "on" : "off")}
            title={llmEnabled ? `Using ${health?.model}` : "Set ANTHROPIC_API_KEY or GROQ_API_KEY in .env to enable AI questions"}
          >
            <span className="dot" /> <span className="hide-sm">{llmEnabled ? `${aiName} ready` : "AI off"}</span>
          </span>
          <button
            className="icon-btn"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            title="Toggle theme"
          >
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
        </div>
      </header>

      <div className="layout">
        <aside className={"sidebar" + (sidebarOpen ? " open" : "")}>
          <div className="sidebar-tabs" role="tablist">
            <button role="tab" aria-selected={tab === "schema"} className={tab === "schema" ? "active" : ""} onClick={() => setTab("schema")}>
              <Database size={14} /> Schema
            </button>
            <button role="tab" aria-selected={tab === "history"} className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}>
              <HistoryIcon size={14} /> History {history.length > 0 && <span className="badge">{history.length}</span>}
            </button>
          </div>
          <div className="sidebar-body">
            {tab === "schema" ? (
              <SchemaPanel schema={schema} loading={schemaLoading} error={schemaError} onPreview={previewTable} />
            ) : (
              <HistoryPanel items={history} onOpen={openHistory} onStar={starHistory} onDelete={deleteHistory} onClear={clearHistory} />
            )}
          </div>
        </aside>
        {sidebarOpen && <div className="scrim mobile-only" onClick={() => setSidebarOpen(false)} />}

        <main className="main">
          <div className="conversation">
            {turns.length === 0 ? (
              <section className="welcome">
                <h1>Ask your data anything</h1>
                <p className="muted">
                  {db?.description ? db.description.replace(/([^.!?])$/, "$1.") : "Type a question in plain English."}{" "}
                  {aiName} writes the SQL, the app runs it read-only, and you get the answer as a table or chart.
                </p>
                {!llmEnabled && health && (
                  <div className="notice info">
                    <div>
                      <strong>AI questions are turned off.</strong>
                      <p>
                        Add <code>GROQ_API_KEY=…</code> (free) or <code>ANTHROPIC_API_KEY=…</code> to the <code>.env</code>{" "}
                        file and restart the server. You can still browse the schema and run your own SQL.
                      </p>
                    </div>
                  </div>
                )}
                {examples.length > 0 && llmEnabled && (
                  <div className="examples">
                    <span className="label">Try one of these</span>
                    <div className="chips">
                      {examples.map((q) => (
                        <button key={q} className="chip" onClick={() => ask(q)} disabled={busy}>
                          {q}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </section>
            ) : (
              <>
                <div className="conversation-head">
                  <button className="ghost-btn" onClick={newConversation} disabled={busy}>
                    <MessageSquarePlus size={15} /> New conversation
                  </button>
                </div>
                {turns.map((t) => (
                  <TurnCard
                    key={t.id}
                    turn={t}
                    schema={schema}
                    dialect={db?.dialect ?? "sqlite"}
                    theme={theme}
                    onRun={rerun}
                    dbName={dbName}
                    onSwitchDb={switchToAnswerDb}
                  />
                ))}
              </>
            )}
            <div ref={endRef} />
          </div>

          <Composer
            mode={mode}
            onModeChange={setMode}
            question={question}
            onQuestionChange={setQuestion}
            sql={sqlDraft}
            onSqlChange={setSqlDraft}
            onSubmit={submit}
            busy={busy}
            llmEnabled={llmEnabled}
            followUp={turns.some((t) => t.status === "done" && !!t.sql)}
            schema={schema}
            dialect={db?.dialect ?? "sqlite"}
            theme={theme}
            resetKey={composerKey}
          />
        </main>
      </div>

      <UploadDialog open={uploadOpen} uploadedDatabases={uploaded} onClose={() => setUploadOpen(false)} onUploaded={onUploaded} />

      {toast && (
        <div className={"toast " + toast.kind} role="status">
          {toast.text}
        </div>
      )}
    </div>
  );
}
