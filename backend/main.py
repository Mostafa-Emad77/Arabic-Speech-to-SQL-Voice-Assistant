import asyncio
import base64
import csv
import io
import logging
import os
import re
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
from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from data_upload import create_database_from_files, drop_temp_database
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
        "data_source": "demo",
        "temp_db_name": None,
        "table_names": [],
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.runtime = _build_runtime_state()
    app.state.runtime_lock = asyncio.Lock()
    logger.info("Application startup complete.")
    yield

    runtime = app.state.runtime
    # Close connection before dropping the database
    db_connection = runtime.get("db_connection")
    if db_connection:
        try:
            db_connection.close()
        except Exception:
            pass

    temp_db = runtime.get("temp_db_name")
    if temp_db:
        drop_temp_database(temp_db)


app = FastAPI(title="Arabic Speech-to-SQL Assistant", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=500)
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
    max_retries = runtime["security_config"].max_sql_retries
    sql_query = ""
    results: list[tuple[Any, ...]] | None = None
    column_names: list[str] | None = None
    metadata: dict[str, Any] = {}

    for attempt in range(max_retries + 1):
        try:
            sql_query = ava.text_to_sql(arabic_text, runtime["db_schema"])
        except RuntimeError:
            if attempt < max_retries:
                logger.warning("SQL generation failed on attempt %d/%d, retrying...", attempt + 1, max_retries + 1)
                continue
            return JSONResponse({"error": "Failed to generate a valid SQL query."}, status_code=400)

        results, column_names, metadata = _execute_query_with_metadata(sql_query, runtime)

        if results is not None and len(results) > 0:
            break

        if attempt < max_retries:
            reason = "empty results" if results is not None else "DB execution failed"
            logger.warning("Query returned %s on attempt %d/%d, retrying...", reason, attempt + 1, max_retries + 1)

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


def _parse_schema_columns(db_schema: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """Parse CREATE TABLE statements and return [(table_name, [(col_name, col_type)])]."""
    tables: list[tuple[str, list[tuple[str, str]]]] = []
    for block in re.split(r"(?=CREATE\s+TABLE)", db_schema, flags=re.IGNORECASE):
        m = re.match(r"CREATE\s+TABLE\s+`?([^`\s(]+)`?\s*\((.*?)\);", block, re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        tname = m.group(1)
        cols: list[tuple[str, str]] = []
        for line in m.group(2).split("\n"):
            line = line.strip().rstrip(",")
            cm = re.match(r"`?([^`\s]+)`?\s+(\S+)", line)
            if cm:
                cols.append((cm.group(1), cm.group(2).upper()))
        tables.append((tname, cols))
    return tables


def _generate_suggestions(db_schema: str) -> list[dict[str, str]]:
    """Generate 3 Arabic question suggestions based on the current schema."""
    tables = _parse_schema_columns(db_schema)
    if not tables:
        return []

    suggestions: list[dict[str, str]] = []

    for tname, cols in tables:
        # Count question
        suggestions.append({
            "text": f"كم عدد السجلات في {tname}",
            "query": f"كم عدد السجلات في جدول {tname}؟",
        })

        # Text columns → show distinct values
        text_cols = [c for c, t in cols if "VARCHAR" in t or "TEXT" in t]
        if text_cols:
            col_display = " و".join(text_cols[:2])
            suggestions.append({
                "text": f"أظهر {col_display} من {tname}",
                "query": f"أظهر {col_display} من جدول {tname}",
            })

        # Numeric columns → aggregate
        num_cols = [c for c, t in cols if any(k in t for k in ("INT", "FLOAT", "DECIMAL", "DOUBLE"))]
        # Exclude likely primary-key columns
        num_cols = [c for c in num_cols if c.lower() not in ("id", "رقم")]
        if num_cols:
            suggestions.append({
                "text": f"ما أعلى {num_cols[0]} في {tname}",
                "query": f"ما هو أعلى {num_cols[0]} في جدول {tname}؟",
            })

    return suggestions[:3]


@app.get("/data_status")
def data_status(request: Request):
    runtime = _runtime(request)
    return {
        "source": runtime["data_source"],
        "tables": runtime["table_names"],
        "test_mode": runtime["test_mode"],
        "suggestions": _generate_suggestions(runtime["db_schema"]),
    }


@app.post("/upload_data")
async def upload_data(request: Request, files: list[UploadFile] = File(...)):
    runtime = _runtime(request)

    try:
        file_data: list[tuple[str, bytes]] = []
        for f in files:
            content = await f.read()
            file_data.append((f.filename or "data.csv", content))

        async with request.app.state.runtime_lock:
            # Always close old connection first, then drop its database
            old_conn = runtime.get("db_connection")
            if old_conn:
                try:
                    old_conn.close()
                except Exception:
                    pass

            old_temp = runtime.get("temp_db_name")
            if old_temp:
                await asyncio.to_thread(drop_temp_database, old_temp)

            connection, db_name, schema_string, table_names = await asyncio.to_thread(
                create_database_from_files, file_data
            )

            runtime["db_connection"] = connection
            runtime["db_schema"] = schema_string
            runtime["test_mode"] = False
            runtime["data_source"] = "uploaded"
            runtime["temp_db_name"] = db_name
            runtime["table_names"] = table_names

        logger.info("User uploaded %d file(s), created DB '%s' with tables: %s", len(files), db_name, table_names)

        return {
            "success": True,
            "db_name": db_name,
            "tables": table_names,
            "message": f"تم إنشاء {len(table_names)} جدول بنجاح",
        }
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:
        logger.exception("Upload failed")
        return JSONResponse({"error": "فشل في معالجة الملفات المرفوعة"}, status_code=500)


@app.post("/reset_data")
async def reset_data(request: Request):
    runtime = _runtime(request)

    async with request.app.state.runtime_lock:
        # Always close old connection first, then drop its database
        old_conn = runtime.get("db_connection")
        if old_conn:
            try:
                old_conn.close()
            except Exception:
                pass

        temp_db = runtime.get("temp_db_name")
        if temp_db:
            await asyncio.to_thread(drop_temp_database, temp_db)

        # Reconnect to demo database
        db_connection = await asyncio.to_thread(
            ava.connect_to_db,
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
        )

        if db_connection:
            db_schema = await asyncio.to_thread(ava.get_db_schema, db_connection)
            test_mode = False
        else:
            db_schema = ava.example_db_schema
            test_mode = True

        runtime["db_connection"] = db_connection
        runtime["db_schema"] = db_schema
        runtime["test_mode"] = test_mode
        runtime["data_source"] = "demo"
        runtime["temp_db_name"] = None
        runtime["table_names"] = []

    logger.info("Reset to demo database")
    return {"success": True, "source": "demo", "message": "تم الرجوع إلى البيانات التجريبية"}


if __name__ == "__main__":
    import uvicorn

    debug_mode = os.getenv("DEBUG", "false").lower() == "true"
    host = os.getenv("FASTAPI_HOST", "127.0.0.1")
    port = int(os.getenv("FASTAPI_PORT", "5000"))
    uvicorn.run(app, host=host, port=port, reload=debug_mode, log_level="info", access_log=True)
