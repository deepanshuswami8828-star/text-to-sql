# Text-to-SQL

Ask questions about your data in plain English and get the answer as a table or a chart.
[Claude](https://www.anthropic.com/claude) writes the SQL, the app checks that it only reads data, runs it,
and fixes the query by itself if the database returns an error.

It's a website that runs on your computer: start it and open **http://localhost:8000** in Chrome (or any browser).

![Asking for monthly revenue and getting SQL plus a line chart](docs/answer-chart.png)

## Features

- **Plain-English questions → SQL.** Follow-up questions ("now only for Mumbai") use the conversation so far.
- **Self-correcting.** If a query fails, Claude sees the error and repairs it (up to 2 times by default).
- **Read-only by design.** Only single `SELECT` queries are allowed, the database connection itself is read-only,
  queries time out after 15 seconds and results are capped at 1,000 rows.
- **Editable SQL.** Every answer shows the SQL in an editor with highlighting and autocomplete. Change it and press Run.
- **Write SQL yourself.** Switch to *Write SQL* mode; this works even without an API key.
- **Tables and charts.** Sortable, paginated results, automatic bar/line charts, and CSV download.
- **Bring your own data.** Upload CSV files (each becomes a table) or SQLite databases, or connect PostgreSQL/MySQL.
- **Schema browser** with tables, columns, keys, relationships and one-click previews.
- **History** of every question and query, with stars for the ones you want to keep.
- **Light and dark themes**, works on phones too.
- Ships with a **sample e-commerce database** (customers, products, orders, reviews in INR) so you can try it immediately.

![Dark theme with a results table](docs/answer-table-dark.png)

## Quick start

You need **Python 3.11+** and **Node.js 20+**. Get a Claude API key from the
[Anthropic Console](https://console.anthropic.com/).

### Windows (one click)

Double-click **`start.bat`** (or run it from a terminal). The first run installs everything, builds the website,
creates a `.env` file, and opens the app in your browser. Paste your key into `.env` and run `start.bat` again.

### macOS / Linux

```bash
./start.sh
```

### Manual setup

```bash
# 1. Python backend
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r backend/requirements.txt

# 2. Your API key
copy .env.example .env            # macOS/Linux: cp .env.example .env
# then edit .env and set ANTHROPIC_API_KEY=...

# 3. Build the website
cd frontend
npm install
npm run build
cd ..

# 4. Run
cd backend
python -m app
```

Open **http://localhost:8000**.

### Docker

```bash
cp .env.example .env              # add your key
docker compose up --build
```

Open **http://localhost:8000**. Uploaded files and history are kept in `./data`.

## Using your own data

- **CSV files:** click **Upload data** and pick a `.csv` (comma, semicolon, tab or pipe separated). Column types
  (whole numbers, decimals, text) are detected automatically. You can add more CSVs to the same database as extra tables,
  so you can ask questions that join them.
- **SQLite databases:** upload a `.db`, `.sqlite` or `.sqlite3` file.
- **PostgreSQL / MySQL:** install the driver (`pip install "psycopg[binary]"` or `pip install PyMySQL`) and add the
  connection to `.env`:

  ```ini
  DATABASES=analytics=postgresql+psycopg://readonly:password@localhost:5432/analytics
  ```

  Several databases are separated by `;`. **Use a database user that can only read.** The app also runs every query
  in a read-only transaction, but a read-only user is the real guarantee.

## Configuration

All settings go in `.env` (see [`.env.example`](.env.example)).

| Variable | Default | What it does |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | – | Your Claude API key. Without it, only *Write SQL* mode works. |
| `CLAUDE_MODEL` | `claude-opus-5-5` | Claude model used to write SQL. |
| `CLAUDE_EFFORT` | `medium` | How hard Claude thinks: `low`, `medium`, `high`, `xhigh`, `max`. Higher is slower but better on hard questions. |
| `CLAUDE_FALLBACKS` | `true` | If the model declines a request, retry on a fallback model automatically. |
| `MAX_FIX_ATTEMPTS` | `2` | How many times Claude may repair a failing query. |
| `MAX_ROWS` | `1000` | Most rows returned per query. |
| `QUERY_TIMEOUT_SECONDS` | `15` | Queries running longer are stopped. |
| `MAX_UPLOAD_MB` | `50` | Largest file you can upload. |
| `DATABASES` | – | Extra databases: `name=sqlalchemy_url;name2=url2`. |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | Where the server listens. |

## How it works

```
Browser (React)  ──question──▶  FastAPI  ──schema + question──▶  Claude
                                   │  ◀────── JSON {sql, explanation} ──┘
                                   ▼
                          SQL safety check (sqlglot)
                                   ▼
                     Read-only connection, timeout, row limit
                                   │
                    error? ── send error back to Claude, retry
                                   ▼
                  Browser shows explanation, SQL, table, chart
```

1. The backend reads the database schema: tables, columns, keys, row counts, a few sample rows, and the values of
   short categorical columns (like order `status`). This goes into the prompt so Claude uses exact names and values.
2. Claude replies in a fixed JSON format (structured outputs): whether the question can be answered, the SQL, and a
   short plain-language explanation. The schema part of the prompt is cached, so repeat questions are cheaper.
3. The SQL is parsed with [sqlglot](https://github.com/tobymao/sqlglot). Anything other than a single read query is
   rejected (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ATTACH`, `PRAGMA`, `SELECT ... INTO`, multiple statements, and
   functions like `load_extension` or `pg_sleep`).
4. The query runs on a **read-only** connection (SQLite opens files with `mode=ro` and `query_only`; PostgreSQL and
   MySQL use read-only transactions), with a timeout and a row limit.
5. If the database reports an error, the error goes back to Claude, which writes a corrected query.

## Project structure

```
backend/
  app/
    main.py        API routes; also serves the built website
    llm.py         Claude prompt, structured output, error handling
    service.py     question → SQL → result pipeline with auto-repair
    database.py    database registry, schema reading, read-only execution, uploads
    sql_guard.py   read-only SQL validation
    importer.py    CSV → SQLite import with type detection
    history.py     query history (stored in data/app.db)
    seed.py        builds the sample e-commerce database
    config.py      settings from .env
  tests/           pytest suite (no API key needed; Claude is mocked)
frontend/
  src/
    App.tsx        page layout and state
    components/    composer, answer cards, SQL editor, table, chart, schema, history, upload
    lib/           chart detection, formatting, CSV export
docs/              screenshots
start.bat / start.sh   one-command setup and start
Dockerfile, docker-compose.yml
```

## Development

Run the backend and the website dev server separately to get hot reload:

```bash
# terminal 1
cd backend
RELOAD=1 python -m app          # Windows PowerShell: $env:RELOAD=1; python -m app

# terminal 2
cd frontend
npm run dev                     # opens on http://localhost:5173 and forwards /api to :8000
```

Tests and checks:

```bash
cd backend
pip install -r requirements-dev.txt
pytest                          # 78 tests: SQL safety, schema reading, CSV import, API, Claude request format
ruff check .

cd ../frontend
npm run build                   # type-checks and builds
```

GitHub Actions runs the same checks on every push and pull request.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Status, whether AI is enabled, model name |
| `GET` | `/api/databases` | List databases |
| `GET` | `/api/databases/{id}/schema` | Tables, columns, keys, row counts |
| `GET` | `/api/databases/{id}/examples` | Example questions |
| `POST` | `/api/databases/upload` | Upload a CSV or SQLite file (`file`, optional `database_id` to add a table) |
| `DELETE` | `/api/databases/{id}` | Delete an uploaded database |
| `POST` | `/api/generate` | `{database_id, question, history?}` → SQL, explanation, result |
| `POST` | `/api/execute` | `{database_id, sql}` → result |
| `GET` / `PATCH` / `DELETE` | `/api/history[/{id}]` | List, star, delete history |

Interactive API docs are at **http://localhost:8000/docs** while the server is running.

## Before putting it on the internet

The app has no login. Anyone who can open it can ask questions (which uses your Claude API credits), upload files,
and read every connected database. Run it on your own machine or a private network, or put it behind a login
(for example a reverse proxy with authentication) before exposing it publicly.

## License

[MIT](LICENSE)
