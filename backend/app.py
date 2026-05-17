import os
import csv
import io
import secrets

from flask import Flask, Response, render_template, request, jsonify, session
import arabic_voice_assistant as ava
import base64
import tempfile
import logging
from dotenv import load_dotenv

from security import load_security_config, sanitize_user_prompt, validate_user_prompt

# Load environment variables from .env file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

app = Flask(__name__, template_folder=os.path.join(PROJECT_ROOT, "frontend"))
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
SECURITY_CONFIG = load_security_config()

_secret_key = os.getenv("FLASK_SECRET_KEY", "")
if not _secret_key:
    logger.warning(
        "FLASK_SECRET_KEY is not set. Using a random key — sessions will be invalidated on restart. "
        "Set FLASK_SECRET_KEY in your .env file for persistent sessions."
    )
    _secret_key = secrets.token_hex(32)
app.secret_key = _secret_key

# Initialize models and database connection
transcriber, sql_model, tokenizer, tts_processor, tts_model = ava.initialize_models()
db_connection = ava.connect_to_db(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME")
)

# Get database schema
if db_connection:
    db_schema = ava.get_db_schema(db_connection)
    test_mode = False
else:
    db_schema = ava.example_db_schema
    test_mode = True

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process_text', methods=['POST'])
def process_text():
    arabic_text = sanitize_user_prompt(request.form.get('text', ''))

    is_prompt_safe, prompt_error = validate_user_prompt(arabic_text, SECURITY_CONFIG)
    if not is_prompt_safe:
        return jsonify({'error': prompt_error}), 400

    # Convert to SQL
    sql_query = ava.text_to_sql(sql_model, tokenizer, arabic_text, db_schema,
                                max_retries=SECURITY_CONFIG.max_sql_retries)

    # Enforce read-only SQL before any execution.
    is_safe, validation_error = ava.validate_read_only_sql(sql_query)
    if not is_safe:
        return jsonify({'error': validation_error, 'sql': sql_query}), 400

    # Store the validated query server-side so /export_csv can use it without
    # trusting any SQL that comes from the client.
    session['last_sql'] = sql_query

    # Execute query
    if test_mode:
        results, column_names = ava.test_mode_query(sql_query)
        metadata = {
            'row_limit': None,
            'returned_rows': len(results),
            'overflow': False,
            'csv_export_available': False,
            'export_row_limit': None,
        }
    else:
        results, column_names, metadata = ava.execute_query_with_metadata(
            db_connection,
            sql_query,
            max_rows=SECURITY_CONFIG.max_result_rows,
            enable_csv_export=True,
            export_row_limit=SECURITY_CONFIG.max_export_rows,
        )

    # Format response
    response = ava.format_response(results, column_names, metadata)

    return jsonify({
        'input': arabic_text,
        'sql': sql_query,
        'response': response,
        'metadata': metadata,
    })

@app.route('/process_audio', methods=['POST'])
def process_audio():
    audio_data = request.form.get('audio', '')

    if not audio_data:
        return jsonify({'error': 'No audio data received'}), 400

    # Decode base64 audio data
    try:
        parts = audio_data.split(',', 1)
        encoded_audio = parts[1] if len(parts) == 2 else parts[0]
        audio_bytes = base64.b64decode(encoded_audio)

        # Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        temp_file.write(audio_bytes)
        temp_file.close()

        # Transcribe audio
        arabic_text = sanitize_user_prompt(ava.transcribe_audio(transcriber, temp_file.name))

        is_prompt_safe, prompt_error = validate_user_prompt(arabic_text, SECURITY_CONFIG)
        if not is_prompt_safe:
            return jsonify({'error': prompt_error}), 400

        # Convert to SQL
        sql_query = ava.text_to_sql(sql_model, tokenizer, arabic_text, db_schema,
                                    max_retries=SECURITY_CONFIG.max_sql_retries)

        # Enforce read-only SQL before any execution.
        is_safe, validation_error = ava.validate_read_only_sql(sql_query)
        if not is_safe:
            return jsonify({'error': validation_error, 'sql': sql_query}), 400

        # Store the validated query server-side so /export_csv can use it without
        # trusting any SQL that comes from the client.
        session['last_sql'] = sql_query

        # Execute query
        if test_mode:
            results, column_names = ava.test_mode_query(sql_query)
            metadata = {
                'row_limit': None,
                'returned_rows': len(results),
                'overflow': False,
                'csv_export_available': False,
                'export_row_limit': None,
            }
        else:
            results, column_names, metadata = ava.execute_query_with_metadata(
                db_connection,
                sql_query,
                max_rows=SECURITY_CONFIG.max_result_rows,
                enable_csv_export=True,
                export_row_limit=SECURITY_CONFIG.max_export_rows,
            )

        # Format response
        response = ava.format_response(results, column_names, metadata)

        return jsonify({
            'input': arabic_text,
            'sql': sql_query,
            'response': response,
            'metadata': metadata,
        })
    except Exception as e:
        logger.exception("Audio processing failed: %s", e)
        return jsonify({'error': 'Failed to process audio request'}), 500

@app.route('/text_to_speech', methods=['POST'])
def text_to_speech():
    text = request.form.get('text', '')

    if not text:
        return jsonify({'error': 'No text received'}), 400

    try:
        # Generate speech using the TTS model
        audio_data = ava.generate_speech_for_web(tts_processor, tts_model, text)

        # Convert audio data to base64 for sending to client
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')

        return jsonify({
            'audio': audio_base64
        })
    except Exception as e:
        logger.exception("TTS generation failed: %s", e)
        return jsonify({'error': 'Failed to generate speech'}), 500


@app.route('/export_csv', methods=['POST'])
def export_csv():
    sql_query = session.get('last_sql', '').strip()
    if not sql_query:
        return jsonify({'error': 'No query available to export. Please run a query first.'}), 400

    is_safe, validation_error = ava.validate_read_only_sql(sql_query)
    if not is_safe:
        return jsonify({'error': validation_error}), 400

    if test_mode:
        results, column_names = ava.test_mode_query(sql_query)
        metadata = {'overflow': False, 'row_limit': None, 'returned_rows': len(results)}
    else:
        results, column_names, metadata = ava.execute_query_with_metadata(
            db_connection,
            sql_query,
            max_rows=SECURITY_CONFIG.max_export_rows,
            enable_csv_export=False,
            export_row_limit=SECURITY_CONFIG.max_export_rows,
        )

    if results is None or column_names is None:
        return jsonify({'error': 'Failed to export query results'}), 400

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(column_names)
    writer.writerows(results)

    csv_content = output.getvalue()
    output.close()

    response = Response(csv_content, mimetype='text/csv; charset=utf-8')
    response.headers['Content-Disposition'] = 'attachment; filename="query_results.csv"'
    response.headers['X-Export-Truncated'] = 'true' if metadata.get('overflow') else 'false'
    if metadata.get('row_limit'):
        response.headers['X-Export-Row-Limit'] = str(metadata['row_limit'])
    return response

if __name__ == '__main__':
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))
    app.run(debug=debug_mode, host=host, port=port)
