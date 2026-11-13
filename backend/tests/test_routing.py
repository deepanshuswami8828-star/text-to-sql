"""Answering from another database when the selected one doesn't have the data."""

from app.database import DatabaseRegistry
from app.llm import Generation


def _school_only(question, failures, schema):
    """Fake AI that can only answer from the School database."""
    if "CREATE TABLE students" in schema:
        return Generation(True, "SELECT ROUND(AVG(marks_obtained), 2) AS avg_marks FROM marks", "Average marks.")
    return Generation(False, "", "No student data here.")


def test_routes_to_the_database_that_has_the_data(client, fake_generator):
    fake_generator.script = _school_only
    fake_generator.route_to = "school"
    body = client.post("/api/generate", json={"database_id": "ecommerce",
                                              "question": "find the average marks of students"}).json()
    assert body["answerable"] is True
    assert body["database_id"] == "school"
    assert body["routed_from"] == "ecommerce"
    assert body["result"]["columns"] == ["avg_marks"]
    assert 30 < body["result"]["rows"][0][0] < 90
    # the catalog shown to the AI lists the other databases, not the selected one
    catalog = fake_generator.route_calls[0]["catalog"]
    assert "id: school" in catalog and "marks(" in catalog and "id: ecommerce" not in catalog
    # saved in the history of the database that answered
    history = client.get("/api/history", params={"database_id": "school"}).json()
    assert history[0]["question"] == "find the average marks of students"


def test_no_route_keeps_the_original_explanation(client, fake_generator):
    fake_generator.script = [Generation(False, "", "There is no weather data.")]
    fake_generator.route_to = None
    body = client.post("/api/generate", json={"database_id": "ecommerce", "question": "weather in Pune?"}).json()
    assert body["answerable"] is False
    assert body["database_id"] == "ecommerce"
    assert body["routed_from"] is None
    assert body["explanation"] == "There is no weather data."


def test_unknown_or_same_route_target_is_ignored(client, fake_generator):
    fake_generator.script = [Generation(False, "", "nope")]
    for target in ("does_not_exist", "ecommerce"):
        fake_generator.route_to = target
        body = client.post("/api/generate", json={"database_id": "ecommerce", "question": "x"}).json()
        assert body["answerable"] is False and body["routed_from"] is None
    assert len(fake_generator.calls) == 2  # never generated on another database


def test_routing_can_be_turned_off(client, fake_generator):
    fake_generator.script = _school_only
    fake_generator.route_to = "school"
    body = client.post("/api/generate", json={"database_id": "ecommerce", "question": "marks?",
                                              "auto_route": False}).json()
    assert body["answerable"] is False
    assert fake_generator.route_calls == []


def test_answerable_questions_are_not_routed(client, fake_generator):
    fake_generator.route_to = "school"
    body = client.post("/api/generate", json={"database_id": "ecommerce", "question": "how many customers"}).json()
    assert body["database_id"] == "ecommerce" and body["routed_from"] is None
    assert fake_generator.route_calls == []


def test_catalog_text(registry: DatabaseRegistry):
    text = registry.catalog_text(exclude="company")
    assert "id: company" not in text
    for db_id in ("ecommerce", "government", "school"):
        assert f"id: {db_id}" in text
    assert "grievances(grievance_id" in text


def test_company_and_government_samples(registry: DatabaseRegistry):
    _, heads = registry.execute(
        "company",
        "SELECT d.name, e.level FROM departments d JOIN employees e ON e.employee_id = d.head_employee_id",
    )
    assert heads.row_count == 8 and all(level == "L5" for _, level in heads.rows)
    _, payroll = registry.execute("company", "SELECT MIN(month), MAX(month) FROM payroll")
    assert payroll.rows == [["2025-01", "2026-10"]]

    _, states = registry.execute("government", "SELECT name FROM states ORDER BY literacy_rate DESC LIMIT 1")
    assert states.rows == [["Kerala"]]
    _, alloc = registry.execute(
        "government", "SELECT COUNT(*) FROM scheme_allocations WHERE spent_crore > allocated_crore"
    )
    assert alloc.rows == [[0]]
    assert "not official statistics" in registry.get("government").description
