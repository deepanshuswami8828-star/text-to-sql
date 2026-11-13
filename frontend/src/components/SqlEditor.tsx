import { useMemo, useRef } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { MSSQL, MySQL, PostgreSQL, SQLite, StandardSQL, sql, type SQLDialect } from "@codemirror/lang-sql";
import { EditorView, keymap } from "@codemirror/view";
import { Prec } from "@codemirror/state";
import type { Schema, Theme } from "../types";

const DIALECTS: Record<string, SQLDialect> = {
  sqlite: SQLite,
  postgresql: PostgreSQL,
  mysql: MySQL,
  mariadb: MySQL,
  mssql: MSSQL,
};

interface Props {
  value: string;
  onChange?: (value: string) => void;
  onRun?: () => void;
  dialect?: string;
  schema?: Schema | null;
  theme: Theme;
  minHeight?: string;
  maxHeight?: string;
  placeholder?: string;
  autoFocus?: boolean;
  readOnly?: boolean;
}

/** SQL editor with syntax highlighting, schema-aware autocomplete and Ctrl/Cmd+Enter to run. */
export function SqlEditor({
  value,
  onChange,
  onRun,
  dialect = "sqlite",
  schema,
  theme,
  minHeight = "64px",
  maxHeight = "340px",
  placeholder,
  autoFocus,
  readOnly,
}: Props) {
  const runRef = useRef(onRun);
  runRef.current = onRun;

  const extensions = useMemo(() => {
    const tables: Record<string, string[]> = {};
    for (const t of schema?.tables ?? []) tables[t.name] = t.columns.map((c) => c.name);
    return [
      sql({ dialect: DIALECTS[dialect] ?? StandardSQL, schema: tables, upperCaseKeywords: true }),
      Prec.highest(
        keymap.of([
          {
            key: "Mod-Enter",
            run: () => {
              runRef.current?.();
              return true;
            },
          },
        ]),
      ),
      EditorView.lineWrapping,
    ];
  }, [dialect, schema]);

  return (
    <CodeMirror
      className="sql-editor"
      value={value}
      onChange={onChange}
      extensions={extensions}
      theme={theme}
      minHeight={minHeight}
      maxHeight={maxHeight}
      placeholder={placeholder}
      autoFocus={autoFocus}
      readOnly={readOnly}
      editable={!readOnly}
      basicSetup={{
        lineNumbers: false,
        foldGutter: false,
        highlightActiveLine: false,
        highlightActiveLineGutter: false,
      }}
    />
  );
}
