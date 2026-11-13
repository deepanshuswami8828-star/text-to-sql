import io
import sqlite3

from app.llm import Generation


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["llm_enabled"] is True
    assert body["max_rows"] == 50


def test_health_without_api_key(client_without_llm):
    assert client_without_llm.get("/api/health").json()["llm_enabled"] is False


def test_list_databases_and_schema(client):
    dbs = client.get("/api/databases").json()
    assert [d["id"] for d in dbs] == ["ecommerce", "school"]
    assert dbs[0] == {
        "id": "ecommerce", "name": "E-commerce (sample)", "kind": "sample", "dialect": "sqlite",
        "description": dbs[0]["description"], "deletable": False,
    }
    schema = client.get("/api/databases/ecommerce/schema").json()
    assert schema["dialect"] == "sqlite"
    assert {t["name"] for t in schema["tables"]} >= {"orders", "customers"}


def test_unknown_database_is_404(client):
    r = client.get("/api/databases/nope/schema")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


def test_examples_for_sample(client):
    examples = client.get("/api/databases/ecommerce/examples").json()
    assert len(examples) >= 5 and all(isinstance(q, str) for q in examples)
    school = client.get("/api/databases/school/examples").json()
    assert school[0] == "Find the average marks of students in each subject"


def test_execute_success_is_saved_to_history(client):
    r = client.post("/api/execute", json={"database_id": "ecommerce", "sql": "SELECT COUNT(*) AS n FROM orders"})
    body = r.json()
    assert r.status_code == 200
    assert body["error"] is None
    assert body["result"]["rows"] == [[2000]]
    hist = client.get("/api/history").json()
    assert hist[0]["id"] == body["history_id"]
    assert hist[0]["source"] == "manual" and hist[0]["row_count"] == 1


def test_execute_blocked_sql_returns_error_not_500(client):
    body = client.post("/api/execute", json={"database_id": "ecommerce", "sql": "DROP TABLE orders"}).json()
    assert body["result"] is None
    assert "DROP" in body["error"]


def test_generate_runs_generated_sql(client, fake_generator):
    fake_generator.script = [Generation(True, "SELECT COUNT(*) AS customers FROM customers", "Counts customers.")]
    body = client.post("/api/generate", json={"database_id": "ecommerce", "question": "How many customers?"}).json()
    assert body["answerable"] is True
    assert body["result"]["rows"] == [[300]]
    assert body["explanation"] == "Counts customers."
    assert body["attempts"] == []
    assert body["history_id"] is not None
    call = fake_generator.calls[0]
    assert call["dialect"] == "sqlite"
    assert "CREATE TABLE customers" in call["schema"]


def test_generate_repairs_failing_sql(client, fake_generator):
    fake_generator.script = [
        Generation(True, "SELECT nme FROM customers", "first try"),
        Generation(True, "SELECT first_name FROM customers LIMIT 2", "fixed"),
    ]
    body = client.post("/api/generate", json={"database_id": "ecommerce", "question": "names"}).json()
    assert body["error"] is None
    assert body["sql"] == "SELECT first_name FROM customers LIMIT 2"
    assert len(body["attempts"]) == 1
    assert "no such column" in body["attempts"][0]["error"]
    # Claude was shown the error on the second call
    assert "no such column" in fake_generator.calls[1]["failures"][0].error


def test_generate_gives_up_after_max_attempts(client, fake_generator):
    fake_generator.script = [Generation(True, "SELECT * FROM nowhere", "broken")]
    body = client.post("/api/generate", json={"database_id": "ecommerce", "question": "x"}).json()
    assert len(fake_generator.calls) == 3  # first try + 2 repairs
    assert "no such table" in body["error"]
    assert body["result"] is None
    assert len(body["attempts"]) == 2


def test_generate_unanswerable(client, fake_generator):
    fake_generator.script = [Generation(False, "", "This database has no weather data.")]
    body = client.post("/api/generate", json={"database_id": "ecommerce", "question": "Weather in Pune?"}).json()
    assert body["answerable"] is False
    assert body["sql"] == ""
    assert "weather" in body["explanation"]
    assert body["history_id"] is None


def test_generate_passes_history(client, fake_generator):
    client.post("/api/generate", json={
        "database_id": "ecommerce", "question": "only in Pune",
        "history": [{"question": "count customers", "sql": "SELECT COUNT(*) FROM customers"}],
    })
    assert fake_generator.calls[0]["history"][0].question == "count customers"


def test_generate_without_api_key_is_503(client_without_llm):
    r = client_without_llm.post("/api/generate", json={"database_id": "ecommerce", "question": "hi"})
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_generate_validates_input(client):
    assert client.post("/api/generate", json={"database_id": "ecommerce", "question": ""}).status_code == 422


def test_history_star_delete_clear(client):
    ids = [
        client.post("/api/execute", json={"database_id": "ecommerce", "sql": f"SELECT {i}"}).json()["history_id"]
        for i in range(3)
    ]
    assert client.patch(f"/api/history/{ids[0]}", json={"starred": True}).json()["starred"] is True
    assert client.get("/api/history", params={"starred": True}).json()[0]["id"] == ids[0]

    assert client.delete(f"/api/history/{ids[1]}").status_code == 204
    assert client.delete(f"/api/history/{ids[1]}").status_code == 404

    assert client.delete("/api/history").status_code == 204
    remaining = client.get("/api/history").json()
    assert [h["id"] for h in remaining] == [ids[0]]  # starred items survive "clear"


def test_upload_csv_query_add_table_and_delete(client, tmp_path):
    r = client.post(
        "/api/databases/upload",
        files={"file": ("Sales 2025.csv", b"region,amount\nNorth,10\nSouth,25\nNorth,5\n", "text/csv")},
    )
    assert r.status_code == 201, r.text
    db = r.json()
    assert db["id"] == "sales_2025" and db["deletable"] is True

    body = client.post("/api/execute", json={
        "database_id": "sales_2025",
        "sql": "SELECT region, SUM(amount) AS total FROM sales_2025 GROUP BY region ORDER BY region",
    }).json()
    assert body["result"]["rows"] == [["North", 15], ["South", 25]]

    # add a second CSV as another table in the same database
    r = client.post(
        "/api/databases/upload",
        data={"database_id": "sales_2025"},
        files={"file": ("targets.csv", b"region,target\nNorth,20\nSouth,20\n", "text/csv")},
    )
    assert r.status_code == 201, r.text
    tables = {t["name"] for t in client.get("/api/databases/sales_2025/schema").json()["tables"]}
    assert tables == {"sales_2025", "targets"}

    examples = client.get("/api/databases/sales_2025/examples").json()
    assert examples and all(isinstance(q, str) for q in examples)

    assert client.delete("/api/databases/sales_2025").status_code == 204
    assert [d["id"] for d in client.get("/api/databases").json()] == ["ecommerce", "school"]


def test_upload_sqlite_database(client, tmp_path):
    src = tmp_path / "lib.db"
    conn = sqlite3.connect(src)
    conn.execute("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT)")
    conn.execute("INSERT INTO books VALUES (1, 'Godan')")
    conn.commit()
    conn.close()
    r = client.post("/api/databases/upload", files={"file": ("library.db", io.BytesIO(src.read_bytes()))})
    assert r.status_code == 201
    assert r.json()["id"] == "library"


def test_upload_rejects_unsupported_file(client):
    r = client.post("/api/databases/upload", files={"file": ("x.exe", b"MZ")})
    assert r.status_code == 400
    assert "SQLite" in r.json()["detail"]


def test_cannot_delete_sample_database(client):
    assert client.delete("/api/databases/ecommerce").status_code == 400
