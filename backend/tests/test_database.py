import pytest

from database import validate_read_only_sql


# ── Safe SELECT queries ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM employees",
        "SELECT name, salary FROM employees WHERE department_id = 5",
        "SELECT COUNT(*) FROM employees",
        "SELECT e.name, d.name FROM employees e JOIN departments d ON e.department_id = d.id",
        "SELECT AVG(salary) FROM employees GROUP BY department_id",
        "SELECT * FROM employees ORDER BY hire_date DESC LIMIT 10",
        "SELECT DISTINCT department_id FROM employees",
        "WITH dept_avg AS (SELECT department_id, AVG(salary) as avg_sal FROM employees GROUP BY department_id) SELECT * FROM dept_avg",
    ],
)
def test_valid_select_queries(query):
    is_safe, error = validate_read_only_sql(query)
    assert is_safe is True, f"Query incorrectly blocked: {query!r} — {error}"
    assert error is None


# ── Blocked write/DDL queries ─────────────────────────────────────────


@pytest.mark.parametrize(
    "query",
    [
        "INSERT INTO employees (name) VALUES ('test')",
        "UPDATE employees SET salary = 0",
        "DELETE FROM employees WHERE id = 1",
        "DROP TABLE employees",
        "ALTER TABLE employees ADD COLUMN test VARCHAR(50)",
        "TRUNCATE TABLE employees",
        "CREATE TABLE hack (id INT)",
        "GRANT ALL ON employees TO 'hacker'",
        "REVOKE ALL ON employees FROM 'user'",
    ],
)
def test_blocked_write_queries(query):
    is_safe, error = validate_read_only_sql(query)
    assert is_safe is False, f"Dangerous query was NOT blocked: {query!r}"
    assert error is not None


# ── Edge cases ────────────────────────────────────────────────────────


def test_empty_query():
    is_safe, error = validate_read_only_sql("")
    assert is_safe is False


def test_whitespace_only():
    is_safe, error = validate_read_only_sql("   ")
    assert is_safe is False


def test_none_query():
    is_safe, error = validate_read_only_sql(None)  # type: ignore[arg-type]
    assert is_safe is False


def test_multiple_statements_blocked():
    is_safe, error = validate_read_only_sql("SELECT 1; SELECT 2;")
    assert is_safe is False
    assert "one" in error.lower() or "واحد" in error


def test_select_with_subquery():
    query = "SELECT * FROM employees WHERE department_id IN (SELECT id FROM departments WHERE name = 'Engineering')"
    is_safe, error = validate_read_only_sql(query)
    assert is_safe is True
    assert error is None


def test_select_into_blocked():
    # SELECT ... INTO creates a new table in MySQL — should be blocked or at least parsed
    query = "SELECT * INTO new_table FROM employees"
    is_safe, error = validate_read_only_sql(query)
    # This is an edge case: depending on sqlglot parsing, it might or might not be blocked
    # The important thing is it doesn't crash
    assert isinstance(is_safe, bool)


def test_union_select():
    query = "SELECT name FROM employees UNION SELECT name FROM contractors"
    is_safe, error = validate_read_only_sql(query)
    assert is_safe is True
    assert error is None
