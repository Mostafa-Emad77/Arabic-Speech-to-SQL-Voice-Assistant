import os
from flask import Flask, render_template, request, jsonify
import arabic_voice_assistant as ava
import base64
import tempfile
import numpy as np
import io
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

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
    arabic_text = request.form.get('text', '')
    
    # Convert to SQL
    sql_query = ava.text_to_sql(sql_model, tokenizer, arabic_text, db_schema)
    
    # Execute query
    if test_mode:
        results, column_names = ava.test_mode_query(sql_query)
    else:
        results, column_names = ava.execute_query(db_connection, sql_query)
    
    # Format response
    response = ava.format_response(results, column_names)
    
    return jsonify({
        'input': arabic_text,
        'sql': sql_query,
        'response': response
    })

@app.route('/process_audio', methods=['POST'])
def process_audio():
    audio_data = request.form.get('audio', '')
    
    if not audio_data:
        return jsonify({'error': 'No audio data received'})
    
    # Decode base64 audio data
    try:
        audio_bytes = base64.b64decode(audio_data.split(',')[1])
        
        # Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        temp_file.write(audio_bytes)
        temp_file.close()
        
        # Transcribe audio
        arabic_text = ava.transcribe_audio(transcriber, temp_file.name)
        
        # Convert to SQL
        sql_query = ava.text_to_sql(sql_model, tokenizer, arabic_text, db_schema)
        
        # Execute query
        if test_mode:
            results, column_names = ava.test_mode_query(sql_query)
        else:
            results, column_names = ava.execute_query(db_connection, sql_query)
        
        # Format response
        response = ava.format_response(results, column_names)
        
        return jsonify({
            'input': arabic_text,
            'sql': sql_query,
            'response': response
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/text_to_speech', methods=['POST'])
def text_to_speech():
    text = request.form.get('text', '')
    
    if not text:
        return jsonify({'error': 'No text received'})
    
    try:
        # Generate speech using the TTS model
        audio_data = ava.generate_speech_for_web(tts_processor, tts_model, text)
        
        # Convert audio data to base64 for sending to client
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        return jsonify({
            'audio': audio_base64
        })
    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
