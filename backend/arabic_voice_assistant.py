from typing import Any

from database import (
    connect_to_db,
    execute_query_with_metadata,
    example_db_schema,
    get_db_schema,
    test_mode_query,
    validate_read_only_sql,
)
from response_formatter import format_response
from speech import initialize_asr_model, transcribe_audio
from sql_engine import check_ollama_connection, generate_natural_response, text_to_sql
from tts_engine import generate_speech_for_web, initialize_local_arabic_tts

__all__ = [
    "connect_to_db",
    "example_db_schema",
    "execute_query_with_metadata",
    "format_response",
    "generate_natural_response",
    "generate_speech_for_web",
    "get_db_schema",
    "initialize_models",
    "test_mode_query",
    "text_to_sql",
    "transcribe_audio",
    "validate_read_only_sql",
]


def initialize_models() -> tuple[Any, Any | None, Any | None]:
    transcriber = initialize_asr_model()
    print("Loading Arabic Text-to-SQL model...")
    check_ollama_connection()
    tts_processor, tts_model = initialize_local_arabic_tts()
    return transcriber, tts_processor, tts_model
