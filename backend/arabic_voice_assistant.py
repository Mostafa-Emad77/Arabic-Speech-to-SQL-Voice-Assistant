import os
from typing import Any

from database import (
    connect_to_db,
    execute_query_with_metadata,
    example_db_schema,
    execute_query,
    get_db_schema,
    test_mode_query,
    validate_read_only_sql,
)
from response_formatter import format_response
from security import load_security_config
from speech import initialize_asr_model, record_audio, transcribe_audio
from sql_engine import check_ollama_connection, text_to_sql
from tts_engine import (
    generate_speech_for_web,
    generate_speech_with_local_model,
    initialize_local_arabic_tts,
)

__all__ = [
    "connect_to_db",
    "example_db_schema",
    "execute_query",
    "execute_query_with_metadata",
    "format_response",
    "generate_speech_for_web",
    "generate_speech_with_local_model",
    "get_db_schema",
    "initialize_models",
    "initialize_local_arabic_tts",
    "main",
    "record_audio",
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


def main() -> None:
    transcriber, tts_processor, tts_model = initialize_models()
    db_connection = connect_to_db()
    security_config = load_security_config()

    test_mode = False
    if not db_connection:
        print("Database connection failed. Running in TEST MODE.")
        test_mode = True
        db_schema = example_db_schema
    else:
        db_schema = get_db_schema(db_connection)
        print("Database schema loaded successfully.")

    while True:
        try:
            print("Do you want to use voice input (v) or text input (t)?")
            input_mode = input().lower()

            if input_mode == "v":
                audio_file = record_audio()
                try:
                    arabic_text = transcribe_audio(transcriber, audio_file)
                finally:
                    if os.path.exists(audio_file):
                        os.unlink(audio_file)
                print(f"Transcribed text: {arabic_text}")
            else:
                print("Enter your question in Arabic:")
                arabic_text = input()
                print(f"Text input: {arabic_text}")

            sql_query = None
            for attempt in range(security_config.max_sql_retries + 1):
                try:
                    sql_query = text_to_sql(arabic_text, db_schema)
                    break
                except RuntimeError:
                    if attempt < security_config.max_sql_retries:
                        print(f"Retrying SQL generation ({attempt + 1}/{security_config.max_sql_retries})...")
            print(f"Generated SQL: {sql_query}")

            is_safe, validation_error = validate_read_only_sql(sql_query)
            if not is_safe:
                print(f"Blocked SQL query: {validation_error}")
                results, column_names = None, None
            elif test_mode:
                results, column_names = test_mode_query(sql_query)
            else:
                results, column_names = execute_query(db_connection, sql_query)

            response = format_response(results, column_names)
            print(f"Response: {response}")

            print("Do you want to hear the response? (y/n)")
            if input().lower() == "y":
                if tts_processor is not None and tts_model is not None:
                    generate_speech_with_local_model(tts_processor, tts_model, response)
                else:
                    print("Error: TTS model not available")

        except Exception as e:
            print(f"Error occurred: {e}")
            response = "عذراً، حدث خطأ أثناء معالجة طلبك."
            print(response)

        print("Do you want to ask another question? (y/n)")
        if input().lower() != "y":
            break

    if not test_mode:
        db_connection.close()


if __name__ == "__main__":
    main()
