import os
import re
from typing import Any

import requests

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


def check_ollama_connection() -> None:
    base_url = get_ollama_base_url()
    try:
        response = requests.get(f"{base_url}/api/tags")
        if response.status_code == 200:
            print("Successfully connected to Ollama server")
        else:
            print(f"Warning: Ollama server returned status code {response.status_code}")
    except Exception as e:
        print(f"Warning: Could not connect to Ollama server: {e}")


def generate_resp(messages: list[dict[str, str]], model: Any = None, tokenizer: Any = None) -> str:
    api_url = f"{get_ollama_base_url()}/api/chat"

    try:
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
        response = requests.post(api_url, json=payload)

        if response.status_code == 200:
            result = response.json()
            message_content = result.get("message", {}).get("content", "")
            if message_content:
                return message_content

            print("Ollama response did not include message content")
            return "SELECT * FROM employees LIMIT 5;"

        print(f"API request failed with status code {response.status_code}: {response.text}")
        return "SELECT * FROM employees LIMIT 5;"
    except Exception as e:
        print(f"Error in API request: {e}")
        return "SELECT * FROM employees LIMIT 5;"


def get_sql_query(db_schema: str, arabic_query: str, model: Any = None, tokenizer: Any = None) -> str:
    enhanced_system_message = (
        system_message
        + "\n"
        + "Additional SQL style constraints:\n"
        + "- Generate exactly one SELECT statement.\n"
        + "- Prefer explicit JOIN conditions when multiple tables are used.\n"
        + "- Use LIMIT only when the user asks for top/first/few records or when ordering by rank."
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

    response = generate_resp(messages, model, tokenizer)

    match = re.search(r"```sql\s*(.*?)\s*```", response, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    sql_match = re.search(r"SELECT.*?;", response, re.DOTALL | re.IGNORECASE)
    if sql_match:
        return sql_match.group(0).strip()
    return response.strip()


def text_to_sql(model: Any, tokenizer: Any, text: str, db_schema: str) -> str:
    print("Generating SQL query...")
    return get_sql_query(db_schema, text, model, tokenizer)
