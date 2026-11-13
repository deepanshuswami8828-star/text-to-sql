import type {
  DatabaseInfo,
  ExecuteResponse,
  GenerateResponse,
  Health,
  HistoryItem,
  HistoryTurn,
  Schema,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");

  let res: Response;
  try {
    res = await fetch(`/api${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Can't reach the server. Is the backend running?");
  }

  if (!res.ok) {
    let message = res.statusText || `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const enc = encodeURIComponent;

export const api = {
  health: () => request<Health>("/health"),
  databases: () => request<DatabaseInfo[]>("/databases"),
  schema: (id: string) => request<Schema>(`/databases/${enc(id)}/schema`),
  examples: (id: string) => request<string[]>(`/databases/${enc(id)}/examples`),
  upload: (file: File, databaseId?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (databaseId) form.append("database_id", databaseId);
    return request<DatabaseInfo>("/databases/upload", { method: "POST", body: form });
  },
  deleteDatabase: (id: string) => request<void>(`/databases/${enc(id)}`, { method: "DELETE" }),

  generate: (body: { database_id: string; question: string; history: HistoryTurn[] }, signal?: AbortSignal) =>
    request<GenerateResponse>("/generate", { method: "POST", body: JSON.stringify(body), signal }),
  execute: (body: { database_id: string; sql: string; question?: string; save_to_history?: boolean }) =>
    request<ExecuteResponse>("/execute", { method: "POST", body: JSON.stringify(body) }),

  history: (databaseId: string, starred = false) =>
    request<HistoryItem[]>(`/history?database_id=${enc(databaseId)}&starred=${starred}`),
  starHistory: (id: number, starred: boolean) =>
    request<HistoryItem>(`/history/${id}`, { method: "PATCH", body: JSON.stringify({ starred }) }),
  deleteHistory: (id: number) => request<void>(`/history/${id}`, { method: "DELETE" }),
  clearHistory: (databaseId: string) => request<void>(`/history?database_id=${enc(databaseId)}`, { method: "DELETE" }),
};

export function errorMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e);
}
