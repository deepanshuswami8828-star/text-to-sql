import { useEffect, useRef, useState } from "react";
import { FileUp, Loader2, X } from "lucide-react";
import { api, errorMessage } from "../api";
import type { DatabaseInfo } from "../types";

interface Props {
  open: boolean;
  uploadedDatabases: DatabaseInfo[];
  onClose: () => void;
  onUploaded: (db: DatabaseInfo) => void;
}

const ACCEPT = ".csv,.tsv,.txt,.db,.sqlite,.sqlite3";

export function UploadDialog({ open, uploadedDatabases, onClose, onUploaded }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    const d = dialogRef.current;
    if (!d) return;
    if (open && !d.open) {
      setFile(null);
      setTarget("");
      setError(null);
      d.showModal();
    } else if (!open && d.open) {
      d.close();
    }
  }, [open]);

  const isCsv = !!file && /\.(csv|tsv|txt)$/i.test(file.name);

  const submit = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const db = await api.upload(file, isCsv && target ? target : undefined);
      onUploaded(db);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <dialog ref={dialogRef} className="dialog" onClose={onClose} onCancel={onClose}>
      <div className="dialog-header">
        <h2>Add your data</h2>
        <button className="icon-btn" onClick={onClose} aria-label="Close">
          <X size={16} />
        </button>
      </div>
      <p className="muted">
        Upload a <strong>CSV</strong> file (becomes a table) or a <strong>SQLite</strong> database (.db, .sqlite). Files stay on
        this server.
      </p>

      <div
        className={"dropzone" + (dragging ? " dragging" : "") + (file ? " has-file" : "")}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const f = e.dataTransfer.files?.[0];
          if (f) setFile(f);
        }}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
      >
        <FileUp size={28} />
        {file ? (
          <span>
            <strong>{file.name}</strong> · {(file.size / 1024).toFixed(file.size > 102400 ? 0 : 1)} KB
          </span>
        ) : (
          <span>Drop a file here or click to choose</span>
        )}
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          hidden
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            e.target.value = "";
          }}
        />
      </div>

      {isCsv && uploadedDatabases.length > 0 && (
        <label className="field">
          <span>Add to</span>
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">A new database</option>
            {uploadedDatabases.map((d) => (
              <option key={d.id} value={d.id}>
                Existing database: {d.name} (as a new table)
              </option>
            ))}
          </select>
        </label>
      )}

      {error && <p className="error-text">{error}</p>}

      <div className="dialog-actions">
        <button className="ghost-btn" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button className="primary-btn" onClick={submit} disabled={!file || busy}>
          {busy ? <Loader2 size={14} className="spin" /> : <FileUp size={14} />} Upload
        </button>
      </div>
    </dialog>
  );
}
