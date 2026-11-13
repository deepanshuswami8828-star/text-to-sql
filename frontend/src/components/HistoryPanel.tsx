import { useState } from "react";
import { AlertTriangle, Code2, Sparkles, Star, Trash2 } from "lucide-react";
import { timeAgo } from "../lib/format";
import type { HistoryItem } from "../types";

interface Props {
  items: HistoryItem[];
  onOpen: (item: HistoryItem) => void;
  onStar: (item: HistoryItem) => void;
  onDelete: (item: HistoryItem) => void;
  onClear: () => void;
}

export function HistoryPanel({ items, onOpen, onStar, onDelete, onClear }: Props) {
  const [starredOnly, setStarredOnly] = useState(false);
  const shown = starredOnly ? items.filter((i) => i.starred) : items;

  return (
    <div className="history-panel">
      <div className="history-toolbar">
        <div className="segmented small" role="group" aria-label="Filter history">
          <button className={!starredOnly ? "active" : ""} onClick={() => setStarredOnly(false)}>
            All
          </button>
          <button className={starredOnly ? "active" : ""} onClick={() => setStarredOnly(true)}>
            <Star size={12} /> Starred
          </button>
        </div>
        {items.some((i) => !i.starred) && (
          <button
            className="ghost-btn"
            onClick={() => {
              if (confirm("Clear history for this database? Starred queries are kept.")) onClear();
            }}
          >
            Clear
          </button>
        )}
      </div>

      {shown.length === 0 ? (
        <div className="panel-empty">
          {starredOnly ? "Star a query to keep it here." : "Your questions and queries will appear here."}
        </div>
      ) : (
        <ul className="history-list">
          {shown.map((item) => (
            <li key={item.id} className="history-item">
              <button className="history-main" onClick={() => onOpen(item)} title={item.sql}>
                <span className="history-icon">
                  {item.error ? (
                    <AlertTriangle size={13} className="error-text" />
                  ) : item.source === "ai" ? (
                    <Sparkles size={13} />
                  ) : (
                    <Code2 size={13} />
                  )}
                </span>
                <span className="history-text">
                  <span className="history-title">{item.question || item.sql}</span>
                  <span className="history-meta">
                    {timeAgo(item.created_at)}
                    {item.error ? " · failed" : item.row_count !== null ? ` · ${item.row_count} rows` : ""}
                  </span>
                </span>
              </button>
              <div className="history-actions">
                <button
                  className={"icon-btn" + (item.starred ? " starred" : "")}
                  onClick={() => onStar(item)}
                  aria-label={item.starred ? "Unstar" : "Star"}
                  title={item.starred ? "Unstar" : "Star"}
                >
                  <Star size={14} fill={item.starred ? "currentColor" : "none"} />
                </button>
                <button className="icon-btn" onClick={() => onDelete(item)} aria-label="Delete" title="Delete">
                  <Trash2 size={14} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
