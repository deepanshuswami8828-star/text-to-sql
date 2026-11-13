import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight } from "lucide-react";
import { formatCell } from "../lib/format";
import type { Cell, QueryResult } from "../types";

const PAGE_SIZE = 50;

function compare(a: Cell, b: Cell): number {
  if (a === b) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}

export function ResultsTable({ result }: { result: QueryResult }) {
  const [sort, setSort] = useState<{ col: number; dir: 1 | -1 } | null>(null);
  const [page, setPage] = useState(0);

  const rows = useMemo(() => {
    if (!sort) return result.rows;
    return [...result.rows].sort((r1, r2) => compare(r1[sort.col], r2[sort.col]) * sort.dir);
  }, [result.rows, sort]);

  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const current = Math.min(page, pages - 1);
  const visible = rows.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE);

  if (result.columns.length === 0) return <p className="muted">The query returned no columns.</p>;

  const toggleSort = (col: number) => {
    setPage(0);
    setSort((s) => (s?.col !== col ? { col, dir: 1 } : s.dir === 1 ? { col, dir: -1 } : null));
  };

  return (
    <div className="table-block">
      <div className="table-scroll">
        <table className="results">
          <thead>
            <tr>
              {result.columns.map((name, i) => (
                <th
                  key={i}
                  className={result.column_types[i] === "number" ? "num" : ""}
                  onClick={() => toggleSort(i)}
                  aria-sort={sort?.col === i ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
                  title="Click to sort"
                >
                  <span>{name}</span>
                  {sort?.col === i && (sort.dir === 1 ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              <tr>
                <td colSpan={result.columns.length} className="empty-row">
                  No rows matched.
                </td>
              </tr>
            ) : (
              visible.map((row, r) => (
                <tr key={r}>
                  {row.map((cell, c) => {
                    const text = formatCell(cell, result.columns[c]);
                    return (
                      <td
                        key={c}
                        className={(typeof cell === "number" ? "num" : "") + (cell === null ? " null" : "")}
                        title={text.length > 40 ? text : undefined}
                      >
                        {text}
                      </td>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="pager">
          <button className="icon-btn" onClick={() => setPage(current - 1)} disabled={current === 0} aria-label="Previous page">
            <ChevronLeft size={16} />
          </button>
          <span>
            Rows {current * PAGE_SIZE + 1}–{Math.min((current + 1) * PAGE_SIZE, rows.length)} of {rows.length}
          </span>
          <button
            className="icon-btn"
            onClick={() => setPage(current + 1)}
            disabled={current >= pages - 1}
            aria-label="Next page"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
