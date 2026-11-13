import { useEffect, useRef } from "react";
import { Code2, Loader2, SendHorizontal, Sparkles } from "lucide-react";
import type { Schema, Theme } from "../types";
import { SqlEditor } from "./SqlEditor";

interface Props {
  mode: "ai" | "sql";
  onModeChange: (mode: "ai" | "sql") => void;
  question: string;
  onQuestionChange: (v: string) => void;
  sql: string;
  onSqlChange: (v: string) => void;
  onSubmit: () => void;
  busy: boolean;
  llmEnabled: boolean;
  followUp: boolean;
  schema: Schema | null;
  dialect: string;
  theme: Theme;
  /** Changing this remounts the SQL editor, which is how it gets cleared after a run. */
  resetKey: number;
}

export function Composer(props: Props) {
  const { mode, onModeChange, question, onQuestionChange, sql, onSqlChange, onSubmit, busy, llmEnabled, followUp } = props;
  const textRef = useRef<HTMLTextAreaElement>(null);

  // Grow the textarea with its content.
  useEffect(() => {
    const el = textRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, [question, mode]);

  const canSubmit = !busy && (mode === "ai" ? question.trim().length > 0 && llmEnabled : sql.trim().length > 0);

  return (
    <div className="composer">
      <div className="composer-top">
        <div className="segmented" role="tablist" aria-label="Input mode">
          <button
            role="tab"
            aria-selected={mode === "ai"}
            className={mode === "ai" ? "active" : ""}
            onClick={() => onModeChange("ai")}
          >
            <Sparkles size={14} /> Ask in English
          </button>
          <button
            role="tab"
            aria-selected={mode === "sql"}
            className={mode === "sql" ? "active" : ""}
            onClick={() => onModeChange("sql")}
          >
            <Code2 size={14} /> Write SQL
          </button>
        </div>
        {mode === "ai" && followUp && <span className="hint">Follow-up questions use the conversation so far</span>}
      </div>

      <div className="composer-box">
        {mode === "ai" ? (
          <textarea
            ref={textRef}
            rows={1}
            value={question}
            onChange={(e) => onQuestionChange(e.target.value)}
            placeholder={
              llmEnabled
                ? "Ask a question about your data, in English or Hinglish"
                : "Add an API key to .env to ask in plain English, or switch to Write SQL"
            }
            disabled={!llmEnabled}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                if (canSubmit) onSubmit();
              }
            }}
            aria-label="Question"
            autoFocus
          />
        ) : (
          <div className="composer-editor">
            <SqlEditor
              key={props.resetKey}
              value={sql}
              onChange={onSqlChange}
              onRun={() => canSubmit && onSubmit()}
              dialect={props.dialect}
              schema={props.schema}
              theme={props.theme}
              minHeight="72px"
              maxHeight="240px"
              placeholder="SELECT * FROM … (Ctrl+Enter to run)"
              autoFocus
            />
          </div>
        )}
        <button className="send-btn" onClick={onSubmit} disabled={!canSubmit} aria-label={mode === "ai" ? "Ask" : "Run"}>
          {busy ? <Loader2 size={18} className="spin" /> : <SendHorizontal size={18} />}
        </button>
      </div>
      <p className="composer-foot">
        {mode === "ai"
          ? "Enter to send · Shift+Enter for a new line · Queries are read-only"
          : "Ctrl+Enter to run · Only read-only SELECT queries are allowed"}
      </p>
    </div>
  );
}
