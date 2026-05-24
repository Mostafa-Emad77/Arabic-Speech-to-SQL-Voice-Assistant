import logging
import os
import re
from pathlib import Path

import requests

from database import validate_read_only_sql

logger = logging.getLogger(__name__)

system_message = (
    "You are an Arabic text-to-SQL assistant for MySQL. "
    "Convert the user's Arabic request into one valid read-only SQL query using the provided schema.\n"
    "Primary domain: employee data (employees and directly related tables).\n"
    "Rules:\n"
    "- Use only tables and columns that exist in the provided schema.\n"
    "- Prefer employee-related tables when the question is about people, jobs, salaries, departments, or hiring.\n"
    "- When name columns exist in Arabic and English, prefer Arabic name columns for matching and filtering.\n"
    "- Keep Arabic filter values exactly as provided by the user; do not translate literals.\n"
    "- Use the correct joins based on key relationships in the schema.\n"
    "- For oldest employees use ORDER BY hire_date ASC; for newest employees use ORDER BY hire_date DESC.\n"
    "- Include hire_date in SELECT when sorting by hire_date.\n"
    "- Return SQL only, without explanations or markdown.\n"
)


def get_ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


def get_ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", "llama3.1:8b")


def get_ollama_think() -> bool:
    return os.getenv("OLLAMA_THINK", "false").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_ollama_log_file() -> Path | None:
    explicit_path = os.getenv("OLLAMA_LOG_PATH", "").strip()
    if explicit_path:
        path = Path(explicit_path)
        if path.exists() and path.is_file():
            return path

    local_appdata = os.getenv("LOCALAPPDATA", "").strip()
    candidates = [
        Path(local_appdata) / "Ollama" / "app.log" if local_appdata else None,
        Path.home() / ".ollama" / "logs" / "app.log",
        Path.home() / ".ollama" / "logs" / "server.log",
    ]

    for candidate in candidates:
        if candidate and candidate.exists() and candidate.is_file():
            return candidate
    return None


def _get_ollama_log_tail() -> str:
    include_tail = os.getenv("OLLAMA_INCLUDE_LOG_TAIL", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not include_tail:
        return ""

    log_file = _resolve_ollama_log_file()
    if not log_file:
        return ""

    try:
        tail_lines_raw = os.getenv("OLLAMA_LOG_TAIL_LINES", "25").strip()
        tail_lines = max(1, min(200, int(tail_lines_raw)))
    except ValueError:
        tail_lines = 25

    try:
        lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return ""

    if not lines:
        return ""

    tail = "\n".join(lines[-tail_lines:])
    return f"\nRecent Ollama logs ({log_file}):\n{tail}"


def check_ollama_connection() -> None:
    base_url = get_ollama_base_url()
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=10)
        if response.status_code == 200:
            logger.info("Successfully connected to Ollama server")
            ollama_log_file = _resolve_ollama_log_file()
            if ollama_log_file:
                logger.info("Using Ollama log file: %s", ollama_log_file)
        else:
            logger.warning("Ollama server returned status code %s", response.status_code)
    except Exception as e:
        logger.warning("Could not connect to Ollama server: %s", e)


def generate_resp(messages: list[dict[str, str]]) -> str:
    api_url = f"{get_ollama_base_url()}/api/chat"
    payload = {
        "model": get_ollama_model(),
        "messages": messages,
        "think": get_ollama_think(),
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.8,
            "num_predict": 1024,
        },
    }
    try:
        response = requests.post(api_url, json=payload, timeout=60)
    except Exception as exc:
        raise RuntimeError(f"Ollama API request failed: {exc}{_get_ollama_log_tail()}") from exc

    if response.status_code != 200:
        raise RuntimeError(
            f"Ollama API request failed with status {response.status_code}: {response.text}"
            f"{_get_ollama_log_tail()}"
        )
    message_content = response.json().get("message", {}).get("content", "")
    if not message_content:
        raise RuntimeError(f"Ollama response did not include message content{_get_ollama_log_tail()}")
    return message_content


def get_sql_query(db_schema: str, arabic_query: str) -> str:
    enhanced_system_message = (
        system_message
        + "\n"
        + "Additional SQL style constraints:\n"
        + "- Generate exactly one SELECT statement.\n"
        + "- Prefer explicit JOIN conditions when multiple tables are used.\n"
        + "- Use LIMIT only when the user asks for top/first/few records or when ordering by rank.\n"
        + "- Never use aggregate functions (COUNT, SUM, AVG, MIN, MAX) in ORDER BY without a GROUP BY clause.\n"
        + "- Always include GROUP BY when mixing aggregate and non-aggregate columns in SELECT.\n"
        + "- For 'lowest/highest/top/bottom N' queries, use ORDER BY column ASC/DESC LIMIT N. Never use nested subqueries like WHERE x < (SELECT MIN(x) ...).\n"
        + "- Keep queries simple and flat. Avoid deeply nested subqueries when ORDER BY + LIMIT achieves the same result."
    )

    instruction_message = "\n".join(
        [
            "## DB-Schema:",
            db_schema,
            "",
            "## User-Prompt:",
            arabic_query,
            "# Output SQL:",
            "```SQL",
        ]
    )

    messages = [
        {"role": "system", "content": enhanced_system_message},
        {"role": "user", "content": instruction_message},
    ]

    response = generate_resp(messages)

    match = re.search(r"```sql\s*(.*?)\s*```", response, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    sql_match = re.search(r"SELECT.*?;", response, re.DOTALL | re.IGNORECASE)
    if sql_match:
        return sql_match.group(0).strip()
    return response.strip()


def text_to_sql(text: str, db_schema: str, max_retries: int = 0) -> str:
    logger.info("Generating SQL query...")
    last_query = ""
    attempts = max_retries + 1
    for attempt in range(attempts):
        last_query = get_sql_query(db_schema, text)
        is_safe, _ = validate_read_only_sql(last_query)
        if is_safe:
            return last_query
        if attempt < max_retries:
            logger.warning("SQL validation failed on attempt %d/%d, retrying...", attempt + 1, attempts)
        else:
            logger.warning("SQL validation failed on attempt %d/%d. All retries exhausted.", attempt + 1, attempts)
    return last_query
