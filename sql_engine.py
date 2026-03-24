import json
import os
import re
from typing import Any

import requests

system_message = (
    "You are a highly advanced Arabic text-to-SQL converter. Your mission is to understand first the db schema and relations between it and then accurately transform Arabic "
    "natural language queries into SQL queries with precision and clarity.\n"
    "When the user asks about names or people, always search using the Arabic name fields in the database rather than English name fields.\n"
    "When users ask any data or conditions the query must always try to pull all the data from the database.\n"
    "When handling hiring dates or employment dates:\n"
    "- For oldest employees (earliest hire date), use ORDER BY hire_date ASC since older dates have smaller values (e.g., 2013 is before 2022)\n"
    "- For newest employees (most recent hire date), use ORDER BY hire_date DESC since newer dates have larger values\n"
    "- Always include the hire_date in the SELECT clause when sorting by date\n"
    "When handling department names:\n"
    "- IMPORTANT: Department names in the database are stored in Arabic\n"
    "- NEVER translate department names to English in your SQL queries\n"
    "- Always extract the Arabic department name directly from the user's query\n"
    "- For example, if user asks about 'قسم الإشراف', use WHERE department_name LIKE '%قسم الإشراف%' or '%الإشراف%'\n"
    "- If user asks about 'قسم الأمن', use WHERE department_name LIKE '%قسم الأمن%' or '%الأمن%'\n"
    "- Always use the exact Arabic text from the user's query in your SQL conditions\n"
    "- Always join tables using the correct key relationships based on the schema\n"
    "- IMPORTANT: Never assume column names - always derive them from the provided schema\n"
)


def get_lm_studio_base_url() -> str:
    return os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234").rstrip("/")


def check_lm_studio_connection() -> None:
    base_url = get_lm_studio_base_url()
    try:
        response = requests.get(f"{base_url}/v1/models")
        if response.status_code == 200:
            print("Successfully connected to LM Studio server")
        else:
            print(f"Warning: LM Studio server returned status code {response.status_code}")
    except Exception as e:
        print(f"Warning: Could not connect to LM Studio server: {e}")


def generate_resp(messages: list[dict[str, str]], model: Any = None, tokenizer: Any = None) -> str:
    api_url = f"{get_lm_studio_base_url()}/v1/chat/completions"

    try:
        payload = {
            "messages": messages,
            "temperature": 0.1,
            "top_p": 0.8,
            "max_tokens": 1024,
        }
        headers = {"Content-Type": "application/json"}
        response = requests.post(api_url, headers=headers, data=json.dumps(payload))

        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"]

        print(f"API request failed with status code {response.status_code}: {response.text}")
        return "SELECT * FROM employees LIMIT 5;"
    except Exception as e:
        print(f"Error in API request: {e}")
        return "SELECT * FROM employees LIMIT 5;"


def get_sql_query(db_schema: str, arabic_query: str, model: Any = None, tokenizer: Any = None) -> str:
    enhanced_system_message = (
        system_message
        + "\n"
        + "IMPORTANT: When filtering for Arabic terms in the database:\n"
        + "- Always use the actual Arabic text from the user's query in the LIKE conditions\n"
        + "- For example, if the user mentions 'قسم الأمن', extract 'الأمن' or use the full phrase as appropriate\n"
        + "- Do NOT translate Arabic terms to English in your SQL conditions\n"
        + "- Always determine the correct column names from the provided schema"
    )
    enhanced_system_message += (
        "\n"
        + "IMPORTANT: When filtering for Arabic department names, use the Arabic text in the LIKE condition. "
        + "For example, for 'قسم الأمن', use WHERE d.department_name LIKE '%الأمن%', NOT '%Security%'."
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
