import os
import re
from dataclasses import dataclass


def _parse_int(value: str | None, default: int, min_value: int, max_value: int) -> int:
    try:
        if value is None:
            return default
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    if parsed < min_value:
        return min_value
    if parsed > max_value:
        return max_value
    return parsed


@dataclass(frozen=True)
class SecurityConfig:
    max_prompt_chars: int
    max_sql_retries: int
    max_result_rows: int
    max_export_rows: int
    blocked_prompt_patterns: tuple[re.Pattern[str], ...]


def load_security_config() -> SecurityConfig:
    max_prompt_chars = _parse_int(os.getenv("MAX_PROMPT_CHARS"), default=1200, min_value=50, max_value=8000)
    max_sql_retries = _parse_int(os.getenv("SQL_MAX_RETRIES"), default=2, min_value=0, max_value=5)
    max_result_rows = _parse_int(os.getenv("SQL_MAX_RESULT_ROWS"), default=200, min_value=1, max_value=5000)
    max_export_rows = _parse_int(os.getenv("SQL_MAX_EXPORT_ROWS"), default=20000, min_value=10, max_value=200000)

    patterns = (
        re.compile(r"\b(ignore|bypass|override)\b.{0,30}\b(instruction|system|policy|guardrail)\b", re.IGNORECASE),
        re.compile(r"\b(reveal|show|print|dump)\b.{0,30}\b(system prompt|developer message|hidden prompt)\b", re.IGNORECASE),
        re.compile(r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke)\b", re.IGNORECASE),
        re.compile(r"(--|/\*|\*/)"),
    )

    return SecurityConfig(
        max_prompt_chars=max_prompt_chars,
        max_sql_retries=max_sql_retries,
        max_result_rows=max_result_rows,
        max_export_rows=max_export_rows,
        blocked_prompt_patterns=patterns,
    )


def sanitize_user_prompt(text: str) -> str:
    cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", " ", text or "")
    return cleaned.strip()


def validate_user_prompt(text: str, config: SecurityConfig) -> tuple[bool, str | None]:
    if not text:
        return False, "No text received"

    if len(text) > config.max_prompt_chars:
        return False, f"Prompt is too long. Maximum allowed length is {config.max_prompt_chars} characters."

    for pattern in config.blocked_prompt_patterns:
        if pattern.search(text):
            return False, "Prompt blocked by safety policy."

    return True, None
