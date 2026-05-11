import logging
import os
import re
from typing import Any

import mysql.connector
from sqlglot import exp, parse
from sqlglot.errors import ParseError

from security import load_security_config

logger = logging.getLogger(__name__)
SECURITY_CONFIG = load_security_config()


def connect_to_db(
    host: str | None = None,
    user: str | None = None,
    password: str | None = None,
    database: str | None = None,
) -> Any | None:
    host = host or os.getenv("DB_HOST")
    user = user or os.getenv("DB_USER")
    password = password or os.getenv("DB_PASSWORD")
    database = database or os.getenv("DB_NAME")
    try:
        connection = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
        )
        print("Connected to MySQL database")
        return connection
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None


def get_db_schema(connection: Any) -> str:
    try:
        cursor = connection.cursor()
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()

        schema: list[str] = []
        for table in tables:
            table_name = table[0]
            cursor.execute(f"DESCRIBE {table_name}")
            columns = cursor.fetchall()

            table_schema = f"CREATE TABLE {table_name} (\n"
            for col in columns:
                col_name = col[0]
                col_type = col[1]
                nullable = "NOT NULL" if col[2] == "NO" else "NULL"
                key = "PRIMARY KEY" if col[3] == "PRI" else ""
                table_schema += f"    {col_name} {col_type} {nullable} {key},\n"
            table_schema = table_schema.rstrip(",\n") + "\n);"
            schema.append(table_schema)

        return "\n\n".join(schema)
    except Exception as e:
        print(f"Error getting schema: {e}")
        return example_db_schema


def validate_read_only_sql(query: str) -> tuple[bool, str | None]:
    if not query or not query.strip():
        return False, "Generated SQL query is empty."

    normalized_query = query.strip()
    try:
        statements = parse(normalized_query, read="mysql")
    except ParseError:
        return False, "Generated SQL query is invalid and could not be parsed safely."

    if len(statements) != 1:
        return False, "Only one SQL statement is allowed."

    statement = statements[0]
    if statement is None:
        return False, "Generated SQL query is invalid."

    has_select = statement.find(exp.Select) is not None
    if not has_select:
        return False, "Only read-only SELECT queries are allowed."

    blocked_keywords = [
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "TRUNCATE",
        "CREATE",
        "REPLACE",
        "GRANT",
        "REVOKE",
        "MERGE",
        "CALL",
        "EXEC",
        "EXECUTE",
    ]
    blocked_pattern = r"\b(" + "|".join(blocked_keywords) + r")\b"
    if re.search(blocked_pattern, normalized_query, re.IGNORECASE):
        return False, "Blocked SQL keyword detected. Only SELECT queries are permitted."

    blocked_nodes = {
        "ALTER",
        "CALL",
        "COMMAND",
        "COMMIT",
        "CREATE",
        "DELETE",
        "DROP",
        "GRANT",
        "INSERT",
        "MERGE",
        "REVOKE",
        "ROLLBACK",
        "TRANSACTION",
        "TRUNCATE",
        "TRUNCATETABLE",
        "UPDATE",
    }
    for node in statement.walk():
        if type(node).__name__.upper() in blocked_nodes:
            return False, "Blocked SQL operation detected. Only SELECT queries are permitted."

    return True, None


def execute_query(connection: Any, query: str) -> tuple[list[tuple[Any, ...]] | None, list[str] | None]:
    results, column_names, _ = execute_query_with_metadata(
        connection,
        query,
        max_rows=SECURITY_CONFIG.max_result_rows,
        enable_csv_export=False,
    )
    return results, column_names


def execute_query_with_metadata(
    connection: Any,
    query: str,
    max_rows: int | None,
    enable_csv_export: bool,
    export_row_limit: int | None = None,
) -> tuple[list[tuple[Any, ...]] | None, list[str] | None, dict[str, Any]]:
    metadata: dict[str, Any] = {
        "row_limit": max_rows,
        "returned_rows": 0,
        "overflow": False,
        "csv_export_available": False,
        "export_row_limit": export_row_limit,
    }

    try:
        is_safe, validation_error = validate_read_only_sql(query)
        if not is_safe:
            logger.warning("Blocked unsafe SQL query: %s", query)
            print(f"Blocked SQL query: {validation_error}")
            return None, None, metadata

        cursor = connection.cursor()
        cursor.execute(query)

        if max_rows is None:
            results = cursor.fetchall()
            overflow = False
        else:
            results = cursor.fetchmany(max_rows + 1)
            overflow = len(results) > max_rows
            if overflow:
                logger.warning("Query result exceeded max row limit (%s). Truncating response.", max_rows)
                results = results[:max_rows]

        column_names = [desc[0] for desc in cursor.description] if cursor.description else []
        cursor.close()

        metadata["returned_rows"] = len(results)
        metadata["overflow"] = overflow
        metadata["csv_export_available"] = bool(enable_csv_export and overflow)

        return results, column_names, metadata
    except Exception as e:
        print(f"Error executing query: {e}")
        return None, None, metadata


def test_mode_query(query: str) -> tuple[list[tuple[str, int, str]], list[str]]:
    print(f"TEST MODE: Would execute query: {query}")
    return [
        ("Product A", 100, "Electronics"),
        ("Product B", 200, "Home Goods"),
    ], ["product_name", "price", "category"]


example_db_schema = r"""{
    'Company':
      CREATE TABLE EMPLOYEES (
    EMPLOYEE_ID    NUMBER(6) PRIMARY KEY,
    FIRST_NAME_EN  VARCHAR2(20),
    SECOND_NAME_EN VARCHAR2(20),
    THIRD_NAME_EN  VARCHAR2(20),
    LAST_NAME_EN   VARCHAR2(20),
    FIRST_NAME_AR  NVARCHAR2(20),
    SECOND_NAME_AR NVARCHAR2(20),
    THIRD_NAME_AR  NVARCHAR2(20),
    LAST_NAME_AR   NVARCHAR2(20),
    EMAIL          VARCHAR2(50),
    PHONE_NUMBER   VARCHAR2(20),
    HIRE_DATE      DATE,
    JOB_ID         VARCHAR2(10),
    SALARY         NUMBER(8,2),
    MANAGER_ID     NUMBER(6),
    DEPARTMENT_ID  NUMBER(4)
          Answer the following questions about this schema:
}"""
