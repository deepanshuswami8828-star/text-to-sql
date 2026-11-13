import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Eye, KeyRound, Link2, Loader2, Search, Table2 } from "lucide-react";
import type { Schema } from "../types";

interface Props {
  schema: Schema | null;
  loading: boolean;
  error: string | null;
  onPreview: (table: string) => void;
}

export function SchemaPanel({ schema, loading, error, onPreview }: Props) {
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});

  const tables = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!schema) return [];
    if (!q) return schema.tables;
    return schema.tables.filter(
      (t) => t.name.toLowerCase().includes(q) || t.columns.some((c) => c.name.toLowerCase().includes(q)),
    );
  }, [schema, filter]);

  if (loading) {
    return (
      <div className="panel-empty">
        <Loader2 size={16} className="spin" /> Reading schema…
      </div>
    );
  }
  if (error) return <div className="panel-empty error-text">{error}</div>;
  if (!schema) return null;

  const searching = filter.trim().length > 0;

  return (
    <div className="schema-panel">
      <label className="search">
        <Search size={14} />
        <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter tables & columns" />
      </label>
      <ul className="table-list">
        {tables.map((t) => {
          const isOpen = searching || !!open[t.name];
          return (
            <li key={t.name}>
              <div className="table-row">
                <button
                  className="table-toggle"
                  onClick={() => setOpen((o) => ({ ...o, [t.name]: !o[t.name] }))}
                  aria-expanded={isOpen}
                >
                  {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  <Table2 size={14} className="muted" />
                  <span className="table-name">{t.name}</span>
                  {t.kind === "view" && <span className="tag">view</span>}
                  {t.row_count !== null && <span className="count">{t.row_count.toLocaleString()}</span>}
                </button>
                <button className="icon-btn" title={`Preview ${t.name}`} onClick={() => onPreview(t.name)}>
                  <Eye size={14} />
                </button>
              </div>
              {isOpen && (
                <ul className="column-list">
                  {t.columns.map((c) => (
                    <li key={c.name} title={c.values ? `Values: ${c.values.join(", ")}` : undefined}>
                      <span className="col-icon">
                        {c.primary_key ? (
                          <KeyRound size={12} className="pk" aria-label="Primary key" />
                        ) : c.foreign_key ? (
                          <Link2 size={12} className="fk" aria-label={`References ${c.foreign_key}`} />
                        ) : null}
                      </span>
                      <span className="col-name">{c.name}</span>
                      <span className="col-type">{c.type.toLowerCase()}</span>
                      {c.foreign_key && <span className="col-ref">→ {c.foreign_key}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
        {tables.length === 0 && <li className="panel-empty">No tables match “{filter}”.</li>}
      </ul>
    </div>
  );
}
