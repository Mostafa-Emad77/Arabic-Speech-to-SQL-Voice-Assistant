"""
Dynamic CSV/Excel upload → MySQL database creation.
Parses uploaded files, infers schema, creates a temporary database,
and populates it with data.
"""

import logging
import os
import re
import uuid
from io import BytesIO
from typing import Any

import mysql.connector
import pandas as pd

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_MB = 10
MAX_TOTAL_SIZE_MB = 50
MAX_FILES = 10
TEMP_DB_PREFIX = "faheem_upload"


def _get_admin_connection() -> Any:
    """Connect to MySQL without selecting a specific database."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
    )


def _sanitize_name(name: str) -> str:
    """Sanitize a string for use as a MySQL table/column name."""
    # Remove file extension
    name = re.sub(r"\.[^.]+$", "", name)
    # Replace non-alphanumeric/Arabic chars with underscores
    name = re.sub(r"[^\w\u0600-\u06FF]", "_", name)
    # Collapse multiple underscores
    name = re.sub(r"_+", "_", name).strip("_")
    # Ensure it doesn't start with a digit
    if name and name[0].isdigit():
        name = f"t_{name}"
    return name[:64] or "table_data"


def _infer_mysql_type(series: pd.Series) -> str:
    """Map a pandas Series dtype to a MySQL column type."""
    dtype = series.dtype

    if pd.api.types.is_integer_dtype(dtype):
        max_val = series.dropna().abs().max() if not series.dropna().empty else 0
        if max_val <= 2147483647:
            return "INT"
        return "BIGINT"

    if pd.api.types.is_float_dtype(dtype):
        return "DECIMAL(15,2)"

    if pd.api.types.is_bool_dtype(dtype):
        return "TINYINT(1)"

    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "DATETIME"

    # Try to detect dates in object columns
    if dtype == object:
        sample = series.dropna().head(20)
        if not sample.empty:
            try:
                pd.to_datetime(sample)
                return "DATE"
            except (ValueError, TypeError):
                pass

    # Default: VARCHAR with length based on max observed
    max_len = series.astype(str).str.len().max()
    if pd.isna(max_len):
        max_len = 255
    else:
        max_len = int(max_len)
    if max_len <= 255:
        return f"VARCHAR({max(max_len + 20, 50)})"
    return "TEXT"


def _parse_file(filename: str, content: bytes) -> pd.DataFrame:
    """Parse a CSV or Excel file into a DataFrame."""
    lower = filename.lower()
    if lower.endswith(".csv"):
        # Try UTF-8, fall back to cp1256 (Arabic Windows)
        try:
            df = pd.read_csv(BytesIO(content), encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(BytesIO(content), encoding="cp1256")
    elif lower.endswith(".xlsx"):
        df = pd.read_excel(BytesIO(content), engine="openpyxl")
    elif lower.endswith(".xls"):
        df = pd.read_excel(BytesIO(content), engine="xlrd")
    else:
        raise ValueError(f"نوع الملف غير مدعوم: {filename}")

    # Sanitize column names
    raw_cols = [_sanitize_name(str(col)) or f"col_{i}" for i, col in enumerate(df.columns)]
    # Deduplicate: append _2, _3, ... for repeated names
    seen: dict[str, int] = {}
    deduped: list[str] = []
    for col in raw_cols:
        if col in seen:
            seen[col] += 1
            deduped.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 1
            deduped.append(col)
    df.columns = deduped
    return df


def drop_temp_database(db_name: str) -> None:
    """Drop a temporary database if it exists."""
    if not db_name.startswith(TEMP_DB_PREFIX):
        logger.warning("Refusing to drop non-temp database: %s", db_name)
        return
    try:
        conn = _get_admin_connection()
        cursor = conn.cursor()
        cursor.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("Dropped temp database: %s", db_name)
    except Exception as e:
        logger.error("Failed to drop temp database %s: %s", db_name, e)


def create_database_from_files(
    files: list[tuple[str, bytes]],
) -> tuple[Any, str, str, list[str]]:
    """
    Create a MySQL database from uploaded CSV/Excel files.

    Args:
        files: List of (filename, file_content_bytes)

    Returns:
        (connection, db_name, schema_string, table_names)

    Raises:
        ValueError: on validation errors
    """
    if len(files) > MAX_FILES:
        raise ValueError(f"الحد الأقصى لعدد الملفات هو {MAX_FILES}")

    total_size = sum(len(content) for _, content in files)
    if total_size > MAX_TOTAL_SIZE_MB * 1024 * 1024:
        raise ValueError(f"الحجم الإجمالي يتجاوز {MAX_TOTAL_SIZE_MB} ميجابايت")

    for filename, content in files:
        if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise ValueError(f"الملف {filename} يتجاوز {MAX_FILE_SIZE_MB} ميجابايت")

    # Generate a unique temp DB name
    db_name = f"{TEMP_DB_PREFIX}_{uuid.uuid4().hex[:8]}"

    # Create the database
    admin_conn = _get_admin_connection()
    admin_cursor = admin_conn.cursor()
    admin_cursor.execute(f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    admin_conn.commit()
    admin_cursor.close()
    admin_conn.close()

    # Connect to the new database
    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=db_name,
    )
    cursor = connection.cursor()

    table_names: list[str] = []
    schema_parts: list[str] = []

    for filename, content in files:
        df = _parse_file(filename, content)
        table_name = _sanitize_name(filename)

        # Avoid duplicate table names
        base_name = table_name
        counter = 1
        while table_name in table_names:
            table_name = f"{base_name}_{counter}"
            counter += 1
        table_names.append(table_name)

        # Build CREATE TABLE
        col_defs: list[str] = []
        for col in df.columns:
            mysql_type = _infer_mysql_type(df[col])
            col_defs.append(f"    `{col}` {mysql_type}")

        create_sql = f"CREATE TABLE `{table_name}` (\n" + ",\n".join(col_defs) + "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
        cursor.execute(create_sql)
        schema_parts.append(create_sql)

        # Insert data in batches
        if not df.empty:
            cols = ", ".join(f"`{c}`" for c in df.columns)
            placeholders = ", ".join(["%s"] * len(df.columns))
            insert_sql = f"INSERT INTO `{table_name}` ({cols}) VALUES ({placeholders})"

            # Convert NaN to None for MySQL
            data = df.where(df.notna(), None).values.tolist()
            batch_size = 1000
            for i in range(0, len(data), batch_size):
                batch = data[i:i + batch_size]
                cursor.executemany(insert_sql, batch)

        connection.commit()
        logger.info("Created table '%s' with %d rows from '%s'", table_name, len(df), filename)

    cursor.close()
    schema_string = "\n\n".join(schema_parts)
    return connection, db_name, schema_string, table_names
