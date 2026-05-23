import base64
import csv
import io
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.INFO)
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

import arabic_voice_assistant as ava
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from security import load_security_config, sanitize_user_prompt, validate_user_prompt

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
FRONTEND_FILE = FRONTEND_DIR / "index.html"

load_dotenv(PROJECT_ROOT / ".env")


def _build_test_metadata(results: list[tuple[Any, ...]]) -> dict[str, Any]:
    return {
        "row_limit": None,
        "returned_rows": len(results),
        "overflow": False,
        "csv_export_available": False,
        "export_row_limit": None,
    }


def _build_runtime_state() -> dict[str, Any]:
    logger.info("Initializing runtime state...")
    security_config = load_security_config()

    logger.info("Loading ASR, LLM and TTS models...")
    transcriber, tts_processor, tts_model = ava.initialize_models()
    db_connection = ava.connect_to_db(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
    )

    if db_connection:
        db_schema = ava.get_db_schema(db_connection)
        test_mode = False
        logger.info("Database connected and schema loaded.")
    else:
        db_schema = ava.example_db_schema
        test_mode = True
        logger.warning("Database connection failed. Running in TEST MODE.")

    return {
        "security_config": security_config,
        "transcriber": transcriber,
        "tts_processor": tts_processor,
        "tts_model": tts_model,
        "db_connection": db_connection,
        "db_schema": db_schema,
        "test_mode": test_mode,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.runtime = _build_runtime_state()
    logger.info("Application startup complete.")
    yield

    runtime = app.state.runtime
    db_connection = runtime.get("db_connection")
    if db_connection:
        try:
            db_connection.close()
        except Exception:
            pass


app = FastAPI(title="Arabic Speech-to-SQL Assistant", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


def _runtime(request: Request) -> dict[str, Any]:
    return request.app.state.runtime


def _execute_query_with_metadata(sql_query: str, runtime: dict[str, Any]) -> tuple[list[tuple[Any, ...]] | None, list[str] | None, dict[str, Any]]:
    if runtime["test_mode"]:
        results, column_names = ava.test_mode_query(sql_query)
        metadata = _build_test_metadata(results)
        return results, column_names, metadata

    return ava.execute_query_with_metadata(
        runtime["db_connection"],
        sql_query,
        max_rows=runtime["security_config"].max_result_rows,
        enable_csv_export=True,
        export_row_limit=runtime["security_config"].max_export_rows,
    )


def _process_arabic_text(arabic_text: str, runtime: dict[str, Any]) -> JSONResponse | dict[str, Any]:
    sql_query = ava.text_to_sql(
        arabic_text,
        runtime["db_schema"],
        max_retries=runtime["security_config"].max_sql_retries,
    )

    is_safe, validation_error = ava.validate_read_only_sql(sql_query)
    if not is_safe:
        return JSONResponse({"error": validation_error, "sql": sql_query}, status_code=400)

    results, column_names, metadata = _execute_query_with_metadata(sql_query, runtime)
    response_text = ava.format_response(results, column_names, metadata)

    return {
        "input": arabic_text,
        "sql": sql_query,
        "response": response_text,
        "metadata": metadata,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_FILE)


@app.post("/process_text")
def process_text(request: Request, text: str = Form("")):
    runtime = _runtime(request)
    arabic_text = sanitize_user_prompt(text)

    is_prompt_safe, prompt_error = validate_user_prompt(arabic_text, runtime["security_config"])
    if not is_prompt_safe:
        return JSONResponse({"error": prompt_error}, status_code=400)

    try:
        return _process_arabic_text(arabic_text, runtime)
    except Exception:
        logger.exception("Text processing failed")
        return JSONResponse({"error": "Failed to process text request"}, status_code=500)


@app.post("/process_audio")
def process_audio(request: Request, audio: str = Form("")):
    runtime = _runtime(request)
    if not audio:
        return JSONResponse({"error": "No audio data received"}, status_code=400)

    temp_path = None
    try:
        parts = audio.split(",", 1)
        encoded_audio = parts[1] if len(parts) == 2 else parts[0]
        audio_bytes = base64.b64decode(encoded_audio)

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        temp_file.write(audio_bytes)
        temp_file.close()
        temp_path = temp_file.name

        arabic_text = sanitize_user_prompt(ava.transcribe_audio(runtime["transcriber"], temp_path))

        is_prompt_safe, prompt_error = validate_user_prompt(arabic_text, runtime["security_config"])
        if not is_prompt_safe:
            return JSONResponse({"error": prompt_error}, status_code=400)

        return _process_arabic_text(arabic_text, runtime)
    except Exception:
        logger.exception("Audio processing failed")
        return JSONResponse({"error": "Failed to process audio request"}, status_code=500)
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


@app.post("/text_to_speech")
def text_to_speech(request: Request, text: str = Form("")):
    runtime = _runtime(request)
    if not text:
        return JSONResponse({"error": "No text received"}, status_code=400)

    try:
        audio_data = ava.generate_speech_for_web(runtime["tts_processor"], runtime["tts_model"], text)
        audio_base64 = base64.b64encode(audio_data).decode("utf-8")
        return {"audio": audio_base64}
    except Exception:
        logger.exception("TTS generation failed")
        return JSONResponse({"error": "Failed to generate speech"}, status_code=500)


@app.post("/export_csv")
def export_csv(request: Request, sql: str = Form("")):
    runtime = _runtime(request)
    sql_query = sql.strip()
    if not sql_query:
        return JSONResponse({"error": "No SQL query received"}, status_code=400)

    is_safe, validation_error = ava.validate_read_only_sql(sql_query)
    if not is_safe:
        return JSONResponse({"error": validation_error}, status_code=400)

    if runtime["test_mode"]:
        results, column_names = ava.test_mode_query(sql_query)
        metadata = {"overflow": False, "row_limit": None, "returned_rows": len(results)}
    else:
        results, column_names, metadata = ava.execute_query_with_metadata(
            runtime["db_connection"],
            sql_query,
            max_rows=runtime["security_config"].max_export_rows,
            enable_csv_export=False,
            export_row_limit=runtime["security_config"].max_export_rows,
        )

    if results is None or column_names is None:
        return JSONResponse({"error": "Failed to export query results"}, status_code=400)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(column_names)
    writer.writerows(results)

    csv_content = output.getvalue()
    output.close()

    headers = {
        "Content-Disposition": 'attachment; filename="query_results.csv"',
        "X-Export-Truncated": "true" if metadata.get("overflow") else "false",
    }
    if metadata.get("row_limit"):
        headers["X-Export-Row-Limit"] = str(metadata["row_limit"])

    return Response(content=csv_content, media_type="text/csv; charset=utf-8", headers=headers)


if __name__ == "__main__":
    import uvicorn

    debug_mode = os.getenv("DEBUG", "false").lower() == "true"
    host = os.getenv("FASTAPI_HOST", "127.0.0.1")
    port = int(os.getenv("FASTAPI_PORT", "5000"))
    uvicorn.run(app, host=host, port=port, reload=debug_mode, log_level="info", access_log=True)
