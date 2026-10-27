import csv
from contextlib import contextmanager
import io
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["DATABASE"] = str(BASE_DIR / "instance" / "querycanvas.sqlite3")

SAMPLE_TABLE = "orders_sample"
SAMPLE_DATA = [
    (1001, "2026-01-04", "North", "Desk Lamp", "Home", 3, 38.50),
    (1002, "2026-01-05", "West", "Travel Mug", "Lifestyle", 12, 14.00),
    (1003, "2026-01-06", "South", "Desk Lamp", "Home", 2, 38.50),
    (1004, "2026-01-08", "East", "Notebook Set", "Stationery", 20, 8.25),
    (1005, "2026-01-10", "North", "Travel Mug", "Lifestyle", 8, 14.00),
    (1006, "2026-01-12", "West", "Notebook Set", "Stationery", 15, 8.25),
    (1007, "2026-01-14", "South", "Cable Organizer", "Tech", 10, 11.50),
    (1008, "2026-01-16", "East", "Desk Lamp", "Home", 4, 38.50),
    (1009, "2026-01-18", "North", "Cable Organizer", "Tech", 7, 11.50),
    (1010, "2026-01-19", "West", "Desk Lamp", "Home", 5, 38.50),
    (1011, "2026-01-21", "South", "Notebook Set", "Stationery", 18, 8.25),
    (1012, "2026-01-22", "East", "Travel Mug", "Lifestyle", 9, 14.00),
    (1013, "2026-01-24", "North", "Desk Lamp", "Home", 2, 38.50),
    (1014, "2026-01-25", "West", "Cable Organizer", "Tech", 14, 11.50),
    (1015, "2026-01-26", "South", "Travel Mug", "Lifestyle", 6, 14.00),
    (1016, "2026-01-27", "East", "Notebook Set", "Stationery", 24, 8.25),
    (1017, "2026-01-28", "North", "Travel Mug", "Lifestyle", 11, 14.00),
    (1018, "2026-01-29", "South", "Cable Organizer", "Tech", 8, 11.50),
    (1019, "2026-01-30", "West", "Notebook Set", "Stationery", 17, 8.25),
    (1020, "2026-01-31", "East", "Cable Organizer", "Tech", 13, 11.50),
]


def get_db():
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session():
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def normalize_column_names(headers):
    """Create safe, unique SQLite column names from CSV headings."""
    names = []
    seen = set()
    for index, header in enumerate(headers, start=1):
        name = re.sub(r"[^a-zA-Z0-9_]", "_", (header or "").strip().lower())
        name = re.sub(r"_+", "_", name).strip("_") or f"column_{index}"
        if name[0].isdigit():
            name = f"col_{name}"
        base = name[:48]
        name = base
        suffix = 2
        while name.lower() in seen:
            tail = f"_{suffix}"
            name = f"{base[:48-len(tail)]}{tail}"
            suffix += 1
        seen.add(name.lower())
        names.append(name)
    return names


def parse_scalar(value):
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    if re.fullmatch(r"[+-]?\d+", value):
        try:
            return int(value)
        except ValueError:
            return value
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\d*\.\d+)(?:[eE][+-]?\d+)?", value):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def quote_identifier(value):
    return '"' + value.replace('"', '""') + '"'


def init_db():
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS datasets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                table_name TEXT NOT NULL UNIQUE,
                columns_json TEXT NOT NULL,
                row_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS saved_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                sql TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
            );
            """
        )
        existing = conn.execute("SELECT id FROM datasets WHERE table_name = ?", (SAMPLE_TABLE,)).fetchone()
        if not existing:
            dataset_id = "sample-orders"
            columns = [
                {"name": "order_id", "type": "INTEGER"},
                {"name": "order_date", "type": "TEXT"},
                {"name": "region", "type": "TEXT"},
                {"name": "product", "type": "TEXT"},
                {"name": "category", "type": "TEXT"},
                {"name": "units", "type": "INTEGER"},
                {"name": "unit_price", "type": "REAL"},
                {"name": "revenue", "type": "REAL"},
            ]
            conn.execute(
                "INSERT INTO datasets (id, name, table_name, columns_json, row_count, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (dataset_id, "Sample orders", SAMPLE_TABLE, json.dumps(columns), len(SAMPLE_DATA), datetime.now(timezone.utc).isoformat()),
            )
            conn.execute(
                f"CREATE TABLE {quote_identifier(SAMPLE_TABLE)} (order_id INTEGER, order_date TEXT, region TEXT, product TEXT, category TEXT, units INTEGER, unit_price REAL, revenue REAL)"
            )
            conn.executemany(
                f"INSERT INTO {quote_identifier(SAMPLE_TABLE)} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(oid, date, region, product, category, units, price, round(units * price, 2)) for oid, date, region, product, category, units, price in SAMPLE_DATA],
            )


def list_datasets():
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM datasets ORDER BY created_at ASC").fetchall()
        return [dataset_from_row(row) for row in rows]


def dataset_from_row(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "table_name": row["table_name"],
        "columns": json.loads(row["columns_json"]),
        "row_count": row["row_count"],
        "created_at": row["created_at"],
    }


def get_dataset(dataset_id):
    with db_session() as conn:
        row = conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
        return dataset_from_row(row) if row else None


def strip_leading_sql_comments(sql):
    text = sql.strip()
    while text:
        if text.startswith("--"):
            newline = text.find("\n")
            if newline < 0:
                return ""
            text = text[newline + 1:].lstrip()
        elif text.startswith("/*"):
            close = text.find("*/", 2)
            if close < 0:
                return ""
            text = text[close + 2:].lstrip()
        else:
            break
    return text


def validate_select_query(sql):
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("Enter a SQL query first.")
    clean = strip_leading_sql_comments(sql)
    if not re.match(r"(?is)^(select|with)\b", clean):
        raise ValueError("Only read-only SELECT queries are allowed.")
    if "\x00" in sql:
        raise ValueError("The query contains an invalid character.")
    return clean


def run_safe_query(dataset, sql, max_rows=200, timeout_seconds=3):
    clean = validate_select_query(sql)
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    allowed_table = dataset["table_name"]
    denied_actions = {
        getattr(sqlite3, name) for name in (
            "SQLITE_INSERT", "SQLITE_UPDATE", "SQLITE_DELETE", "SQLITE_ALTER_TABLE",
            "SQLITE_DROP_TABLE", "SQLITE_DROP_INDEX", "SQLITE_CREATE_TABLE", "SQLITE_CREATE_INDEX",
            "SQLITE_CREATE_TRIGGER", "SQLITE_DROP_TRIGGER", "SQLITE_ATTACH", "SQLITE_DETACH",
            "SQLITE_PRAGMA", "SQLITE_TRANSACTION", "SQLITE_SAVEPOINT", "SQLITE_ANALYZE",
            "SQLITE_REINDEX", "SQLITE_CREATE_VIEW", "SQLITE_DROP_VIEW", "SQLITE_CREATE_VTABLE",
            "SQLITE_DROP_VTABLE",
        ) if hasattr(sqlite3, name)
    }
    allowed_select_actions = {getattr(sqlite3, name) for name in ("SQLITE_SELECT", "SQLITE_READ", "SQLITE_FUNCTION", "SQLITE_RECURSIVE") if hasattr(sqlite3, name)}

    def authorizer(action, arg1, arg2, db_name, trigger_name):
        if action in denied_actions:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_READ:
            if arg1 not in (allowed_table,):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        if action in allowed_select_actions:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    started = time.monotonic()
    conn.set_authorizer(authorizer)
    conn.set_progress_handler(lambda: 1 if time.monotonic() - started > timeout_seconds else 0, 10000)
    try:
        cursor = conn.execute(clean)
        if cursor.description is None:
            raise ValueError("The query did not return a result set. Use SELECT to retrieve rows.")
        columns = [item[0] for item in cursor.description]
        rows = cursor.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        return {
            "columns": columns,
            "rows": [[format_cell(row[col]) for col in columns] for row in rows],
            "row_count": len(rows),
            "truncated": truncated,
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
    except sqlite3.DatabaseError as exc:
        message = str(exc)
        if "not authorized" in message.lower():
            raise ValueError("This query can only read the selected dataset. Writes and other tables are blocked.") from exc
        if "interrupted" in message.lower():
            raise ValueError("This query took too long. Try a simpler query or add a filter.") from exc
        raise ValueError(message) from exc
    finally:
        conn.close()


def format_cell(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return round(value, 6)
    text = str(value)
    return text[:4000] + "…" if len(text) > 4000 else text


def get_saved_queries():
    with db_session() as conn:
        rows = conn.execute(
            "SELECT q.id, q.title, q.sql, q.dataset_id, q.created_at, d.name AS dataset_name "
            "FROM saved_queries q JOIN datasets d ON d.id = q.dataset_id ORDER BY q.id DESC LIMIT 30"
        ).fetchall()
        return [dict(row) for row in rows]


@app.get("/")
def index():
    datasets = list_datasets()
    selected = datasets[0] if datasets else None
    return render_template(
        "index.html",
        datasets=datasets,
        selected=selected,
        saved_queries=get_saved_queries(),
        gemini_ready=bool(os.getenv("GEMINI_API_KEY")),
    )


@app.get("/api/datasets")
def api_datasets():
    return jsonify({"datasets": list_datasets()})


@app.get("/api/datasets/<dataset_id>/preview")
def api_dataset_preview(dataset_id):
    dataset = get_dataset(dataset_id)
    if not dataset:
        return jsonify({"error": "Dataset not found."}), 404
    try:
        result = run_safe_query(dataset, f"SELECT * FROM {quote_identifier(dataset['table_name'])} LIMIT 10", max_rows=10)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@app.post("/api/datasets")
def api_upload_dataset():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "Choose a CSV file to upload."}), 400
    if not uploaded.filename.lower().endswith(".csv"):
        return jsonify({"error": "Please upload a .csv file."}), 400
    try:
        raw = uploaded.stream.read(5 * 1024 * 1024 + 1)
        if len(raw) > 5 * 1024 * 1024:
            return jsonify({"error": "CSV files must be 5 MB or smaller."}), 413
        decoded = raw.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(decoded))
        headers = next(reader, None)
        if not headers or not any((h or "").strip() for h in headers):
            return jsonify({"error": "The CSV needs a header row."}), 400
        clean_headers = normalize_column_names(headers)
        rows = []
        for row in reader:
            if not any((cell or "").strip() for cell in row):
                continue
            row = row[:len(clean_headers)] + [""] * max(0, len(clean_headers) - len(row))
            rows.append([parse_scalar(cell) for cell in row])
            if len(rows) > 50000:
                return jsonify({"error": "CSV files are limited to 50,000 data rows."}), 400
        if not rows:
            return jsonify({"error": "The CSV contains no data rows."}), 400
        if len(clean_headers) > 80:
            return jsonify({"error": "CSV files are limited to 80 columns."}), 400
        dataset_id = uuid.uuid4().hex[:12]
        table_name = f"data_{dataset_id}"
        column_types = []
        for i, name in enumerate(clean_headers):
            values = [row[i] for row in rows if i < len(row) and row[i] is not None]
            if values and all(isinstance(v, int) and not isinstance(v, bool) for v in values):
                sql_type = "INTEGER"
            elif values and all(isinstance(v, (int, float)) for v in values):
                sql_type = "REAL"
            else:
                sql_type = "TEXT"
            column_types.append({"name": name, "type": sql_type})
        table_sql = ", ".join(f"{quote_identifier(col['name'])} {col['type']}" for col in column_types)
        with db_session() as conn:
            conn.execute(f"CREATE TABLE {quote_identifier(table_name)} ({table_sql})")
            placeholders = ", ".join("?" for _ in clean_headers)
            conn.executemany(f"INSERT INTO {quote_identifier(table_name)} VALUES ({placeholders})", rows)
            display_name = Path(uploaded.filename).stem[:80] or "Uploaded dataset"
            conn.execute(
                "INSERT INTO datasets (id, name, table_name, columns_json, row_count, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (dataset_id, display_name, table_name, json.dumps(column_types), len(rows), datetime.now(timezone.utc).isoformat()),
            )
        return jsonify({"dataset": get_dataset(dataset_id)}), 201
    except (UnicodeDecodeError, csv.Error) as exc:
        return jsonify({"error": f"Could not read this CSV: {exc}"}), 400


@app.post("/api/query/run")
def api_run_query():
    payload = request.get_json(silent=True) or {}
    dataset = get_dataset(str(payload.get("dataset_id", "")))
    if not dataset:
        return jsonify({"error": "Choose a dataset first."}), 400
    try:
        result = run_safe_query(dataset, payload.get("sql", ""))
        result["dataset_name"] = dataset["name"]
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/query/ask")
def api_ask_query():
    payload = request.get_json(silent=True) or {}
    dataset = get_dataset(str(payload.get("dataset_id", "")))
    question = str(payload.get("question", "")).strip()
    if not dataset:
        return jsonify({"error": "Choose a dataset first."}), 400
    if not question:
        return jsonify({"error": "Write what you want to find in your data."}), 400
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return jsonify({"error": "AI query generation needs GEMINI_API_KEY in your .env file. You can still write and run SQL manually."}), 400
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        schema_text = "\n".join(f"- {col['name']} ({col['type']})" for col in dataset["columns"])
        prompt = f"""You are a careful SQLite query writer. Return only one read-only SQLite SELECT statement, with no markdown fences and no explanation. Use only this table and its columns. Never use INSERT, UPDATE, DELETE, PRAGMA, ATTACH, or other tables. Do not infer columns that are not listed. Table: {dataset['table_name']}\nColumns:\n{schema_text}\nUser's request: {question}\nAdd a sensible LIMIT 100 when returning detail rows. For aggregate queries, LIMIT is optional."""
        model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        response = client.models.generate_content(model=model, contents=prompt)
        sql = (response.text or "").strip()
        sql = re.sub(r"^```(?:sql)?\s*|\s*```$", "", sql, flags=re.IGNORECASE).strip()
        validate_select_query(sql)
        # Confirm the generated SQL remains confined to this dataset before returning it.
        run_safe_query(dataset, sql, max_rows=1)
        return jsonify({"sql": sql, "model": model})
    except ValueError as exc:
        return jsonify({"error": f"The generated query could not be validated: {exc}"}), 400
    except Exception as exc:
        app.logger.exception("Gemini query generation failed")
        return jsonify({"error": "AI could not generate a safe query. Check your API key/model setting, or write SQL manually."}), 502


@app.post("/api/queries/save")
def api_save_query():
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title", "")).strip()[:80]
    sql = str(payload.get("sql", "")).strip()
    dataset_id = str(payload.get("dataset_id", ""))
    if not title or not sql:
        return jsonify({"error": "Add a query name and SQL before saving."}), 400
    if not get_dataset(dataset_id):
        return jsonify({"error": "Choose a valid dataset."}), 400
    try:
        validate_select_query(sql)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    with db_session() as conn:
        cursor = conn.execute(
            "INSERT INTO saved_queries (title, sql, dataset_id, created_at) VALUES (?, ?, ?, ?)",
            (title, sql, dataset_id, datetime.now(timezone.utc).isoformat()),
        )
        query_id = cursor.lastrowid
    saved = next((q for q in get_saved_queries() if q["id"] == query_id), None)
    return jsonify({"query": saved}), 201


@app.get("/api/queries")
def api_queries():
    return jsonify({"queries": get_saved_queries()})


@app.delete("/api/queries/<int:query_id>")
def api_delete_query(query_id):
    with db_session() as conn:
        cursor = conn.execute("DELETE FROM saved_queries WHERE id = ?", (query_id,))
    if cursor.rowcount == 0:
        return jsonify({"error": "Saved query not found."}), 404
    return jsonify({"ok": True})


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "The uploaded file is too large. The limit is 5 MB."}), 413


init_db()

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true", host="127.0.0.1", port=int(os.getenv("PORT", "5000")))
