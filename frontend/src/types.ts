export type DatabaseKind = "sample" | "upload" | "external";

export interface DatabaseInfo {
  id: string;
  name: string;
  kind: DatabaseKind;
  dialect: string;
  description: string;
  deletable: boolean;
}

export interface Column {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
  foreign_key: string | null;
  values: string[] | null;
}

export interface Table {
  name: string;
  kind: "table" | "view";
  row_count: number | null;
  columns: Column[];
  ddl: string;
  sample_rows: Cell[][];
}

export interface Schema {
  database_id: string;
  dialect: string;
  tables: Table[];
}

export type Cell = string | number | boolean | null;
export type ColumnType = "number" | "text" | "boolean" | "empty";

export interface QueryResult {
  columns: string[];
  column_types: ColumnType[];
  rows: Cell[][];
  row_count: number;
  truncated: boolean;
  elapsed_ms: number;
}

export interface Attempt {
  sql: string;
  error: string;
}

export interface HistoryTurn {
  question: string;
  sql: string;
}

export interface GenerateResponse {
  question: string;
  database_id: string;
  routed_from: string | null;
  answerable: boolean;
  sql: string;
  explanation: string;
  result: QueryResult | null;
  error: string | null;
  attempts: Attempt[];
  history_id: number | null;
}

export interface ExecuteResponse {
  sql: string;
  result: QueryResult | null;
  error: string | null;
  history_id: number | null;
}

export interface HistoryItem {
  id: number;
  database_id: string;
  question: string | null;
  sql: string;
  explanation: string | null;
  row_count: number | null;
  error: string | null;
  source: "ai" | "manual";
  starred: boolean;
  created_at: string;
}

export interface Health {
  status: "ok";
  llm_enabled: boolean;
  provider: "anthropic" | "groq" | null;
  model: string;
  max_rows: number;
  version: string;
}

/** One question (or hand-written query) and its answer in the conversation. */
export interface Turn {
  id: string;
  databaseId: string;
  mode: "ai" | "sql";
  question?: string;
  sql: string;
  explanation?: string;
  answerable?: boolean;
  result?: QueryResult | null;
  error?: string | null;
  attempts?: Attempt[];
  historyId?: number | null;
  /** The database the SQL runs on, when the answer came from a different database than the selected one. */
  queryDb?: string;
  routedFrom?: string | null;
  /** "thinking": waiting for the AI; "running": re-running edited SQL; "done": finished */
  status: "thinking" | "running" | "done";
}

export type Theme = "light" | "dark";
