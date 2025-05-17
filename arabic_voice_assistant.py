import mysql.connector
import torch
from transformers import pipeline, VitsModel, AutoProcessor
from huggingface_hub import InferenceClient
import sounddevice as sd
import soundfile as sf
import tempfile
import os
import re
import requests
import json
import io
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Production-ready system message for SQL generation
system_message = (
    "You are a highly advanced Arabic text-to-SQL converter. Your mission is to understand first the db schema and relations between it and then accurately transform Arabic "
    "natural language queries into SQL queries with precision and clarity.\n" \
    "When the user asks about names or people, always search using the Arabic name fields in the database rather than English name fields.\n"\
    "When users ask any data or conditions the query must always try to pull all the data from the database.\n"\
    "When handling hiring dates or employment dates:\n"\
    "- For oldest employees (earliest hire date), use ORDER BY hire_date ASC since older dates have smaller values (e.g., 2013 is before 2022)\n"\
    "- For newest employees (most recent hire date), use ORDER BY hire_date DESC since newer dates have larger values\n"\
    "- Always include the hire_date in the SELECT clause when sorting by date\n"\
    "When handling department names:\n"
    "- IMPORTANT: Department names in the database are stored in Arabic\n"\
    "- NEVER translate department names to English in your SQL queries\n"\
    "- Always extract the Arabic department name directly from the user's query\n"\
    "- For example, if user asks about 'قسم الإشراف', use WHERE department_name LIKE '%قسم الإشراف%' or '%الإشراف%'\n"\
    "- If user asks about 'قسم الأمن', use WHERE department_name LIKE '%قسم الأمن%' or '%الأمن%'\n"\
    "- Always use the exact Arabic text from the user's query in your SQL conditions\n"\
    "- Always join tables using the correct key relationships based on the schema\n"\
    "- IMPORTANT: Never assume column names - always derive them from the provided schema\n"
)

# Initialize models
def initialize_models():
    print("Loading Whisper model for speech recognition...")
    # Load API key from environment variable
    api_key = os.getenv("FAL_AI_API_KEY")
    client = InferenceClient(
        provider="fal-ai",
        api_key=api_key,
    )
    # We'll use the client directly in the transcribe_audio function
    transcriber = client

    print("Loading Arabic Text-to-SQL model...")
    # LM Studio server endpoint
    base_model_id = "http://127.0.0.1:1234"

    # We'll use requests to communicate with the LM Studio API
    # No need to load the model directly as we'll use the API
    model = None
    tokenizer = None

    # Test connection to LM Studio server
    try:
        response = requests.get(f"{base_model_id}/v1/models")
        if response.status_code == 200:
            print("Successfully connected to LM Studio server")
        else:
            print(f"Warning: LM Studio server returned status code {response.status_code}")
    except Exception as e:
        print(f"Warning: Could not connect to LM Studio server: {e}")

    # Initialize local Arabic TTS model
    tts_processor, tts_model = initialize_local_arabic_tts()

    return transcriber, model, tokenizer, tts_processor, tts_model

# Initialize the local Arabic TTS model
def initialize_local_arabic_tts():
    print("Loading local Arabic TTS model...")
    try:
        model_name = "facebook/mms-tts-ara"  # Arabic TTS model
        processor = AutoProcessor.from_pretrained(model_name)
        model = VitsModel.from_pretrained(model_name)
        return processor, model
    except Exception as e:
        print(f"Error loading local Arabic TTS model: {e}")
        return None, None

# Generate speech with the local model
def generate_speech_with_local_model(processor, model, text):
    try:
        print("Generating speech using local Arabic TTS model...")
        inputs = processor(text=text, return_tensors="pt")
        with torch.no_grad():
            output = model(**inputs).waveform

        # Convert to numpy array for playback
        audio_data = output.squeeze().numpy()

        # Play the audio
        print("Playing response...")
        sd.play(audio_data, samplerate=model.config.sampling_rate)
        sd.wait()
        return True
    except Exception as e:
        print(f"Error generating speech with local model: {e}")
        return False

# Generate speech for web use (returns audio bytes instead of playing)
def generate_speech_for_web(processor, model, text):
    try:
        print("Generating speech using Arabic TTS model...")
        inputs = processor(text=text, return_tensors="pt")
        with torch.no_grad():
            output = model(**inputs).waveform
        
        # Convert to numpy array
        audio_data = output.squeeze().numpy()
        
        # Convert to WAV format
        byte_io = io.BytesIO()
        sf.write(byte_io, audio_data, samplerate=model.config.sampling_rate, format='WAV')
        byte_io.seek(0)
        
        return byte_io.getvalue()
    except Exception as e:
        print(f"Error generating speech: {e}")
        raise e

# Helper function to generate responses using the Gemini API
def generate_resp(messages, model=None, tokenizer=None):
    # We'll use the LM Studio API directly
    api_url = "http://127.0.0.1:1234/v1/chat/completions"

    try:
        payload = {
            "messages": messages,
            "temperature": 0.1,
            "top_p": 0.8,
            "max_tokens": 1024
        }

        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(api_url, headers=headers, data=json.dumps(payload))

        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"]
        else:
            print(f"API request failed with status code {response.status_code}: {response.text}")
            return "SELECT * FROM employees LIMIT 5;"  # Fallback query
    except Exception as e:
        print(f"Error in API request: {e}")
        return "SELECT * FROM employees LIMIT 5;"  # Fallback query

def get_sql_query(db_schema, arabic_query, model=None, tokenizer=None):
    # Add more examples to the system message to improve department filtering
    enhanced_system_message = system_message + "\n" + \
    "IMPORTANT: When filtering for Arabic terms in the database:\n" + \
    "- Always use the actual Arabic text from the user's query in the LIKE conditions\n" + \
    "- For example, if the user mentions 'قسم الأمن', extract 'الأمن' or use the full phrase as appropriate\n" + \
    "- Do NOT translate Arabic terms to English in your SQL conditions\n" + \
    "- Always determine the correct column names from the provided schema"
    
    # Add another example for clarity
    enhanced_system_message += "\n" + \
    "IMPORTANT: When filtering for Arabic department names, use the Arabic text in the LIKE condition. " + \
    "For example, for 'قسم الأمن', use WHERE d.department_name LIKE '%الأمن%', NOT '%Security%'."

    # Construct the instruction message including the DB schema and the Arabic query
    instruction_message = "\n".join([
        "## DB-Schema:",
        db_schema,
        "",
        "## User-Prompt:",
        arabic_query,
        "# Output SQL:",
        "```SQL"
    ])

    messages = [
        {"role": "system", "content": enhanced_system_message},
        {"role": "user", "content": instruction_message}
    ]

    response = generate_resp(messages, model, tokenizer)

    # Extract the SQL query from the response
    match = re.search(r"```sql\s*(.*?)\s*```", response, re.DOTALL | re.IGNORECASE)
    if match:
        sql_query = match.group(1).strip()
        return sql_query
    else:
        # If no SQL code block found, try to extract anything that looks like SQL
        sql_match = re.search(r'SELECT.*?;', response, re.DOTALL | re.IGNORECASE)
        if sql_match:
            return sql_match.group(0).strip()
        return response.strip()

# Get database schema
def get_db_schema(connection):
    try:
        cursor = connection.cursor()
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()

        schema = []
        for table in tables:
            table_name = table[0]
            cursor.execute(f"DESCRIBE {table_name}")
            columns = cursor.fetchall()

            table_schema = f"CREATE TABLE {table_name} (\n"
            for col in columns:
                col_name = col[0]
                col_type = col[1]
                nullable = "NOT NULL" if col[2] == "NO" else "NULL"
                key = "PRIMARY KEY" if col[3] == "PRI" else ""
                table_schema += f"    {col_name} {col_type} {nullable} {key},\n"
            table_schema = table_schema.rstrip(",\n") + "\n);"
            schema.append(table_schema)

        return "\n\n".join(schema)
    except Exception as e:
        print(f"Error getting schema: {e}")
        # Return the example schema as fallback
        return example_db_schema

# Connect to MySQL database
def connect_to_db(host=None, user=None, password=None, database=None):
    # Use environment variables if arguments are not provided
    host = host or os.getenv("DB_HOST")
    user = user or os.getenv("DB_USER")
    password = password or os.getenv("DB_PASSWORD")
    database = database or os.getenv("DB_NAME")
    try:
        connection = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database
        )
        print("Connected to MySQL database")
        return connection
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None

# Record audio from microphone
def record_audio(duration=10, sample_rate=16000):
    print("Recording... Speak now")
    audio_data = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1)
    sd.wait()
    print("Recording finished")

    # Save to temporary file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    sf.write(temp_file.name, audio_data, sample_rate)
    return temp_file.name

# Transcribe Arabic speech to text
def transcribe_audio(transcriber, audio_file):
    try:
        # Open the file in binary mode
        with open(audio_file, "rb") as f:
            audio_content = f.read()
        
        # Use the InferenceClient with raw bytes
        result = transcriber.automatic_speech_recognition(
            audio_content,  # Pass raw bytes directly
            model="openai/whisper-large-v3"
        )
        
        # Clean up temporary file
        os.unlink(audio_file)
        
        # Extract text from result
        text = result["text"].strip() if isinstance(result, dict) else result.strip()
        return text
    except Exception as e:
        print(f"Error in transcription: {e}")
        if os.path.exists(audio_file):
            os.unlink(audio_file)
        return "لم أتمكن من فهم الكلام"  # "I couldn't understand the speech" in Arabic

# Convert Arabic question to SQL query (updated to use the new method)
def text_to_sql(model, tokenizer, text, db_schema):
    print("Generating SQL query...")
    return get_sql_query(db_schema, text, model, tokenizer)

# Execute SQL query and get results
def execute_query(connection, query):
    try:
        cursor = connection.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        column_names = [desc[0] for desc in cursor.description] if cursor.description else []
        cursor.close()
        return results, column_names
    except Exception as e:
        print(f"Error executing query: {e}")
        return None, None

# Format results into Arabic response
def format_response(results, column_names):
    if not results:
        return "لم أجد أي نتائج لهذا الاستعلام."

    response = "وجدت النتائج التالية:\n"
    for row in results:
        row_data = [f"{column_names[i]}: {value}" for i, value in enumerate(row)]
        response += ", ".join(row_data) + "\n"

    return response

# Test mode function to simulate database results
def test_mode_query(query):
    print(f"TEST MODE: Would execute query: {query}")
    # Return some mock data
    return [
        ("Product A", 100, "Electronics"),
        ("Product B", 200, "Home Goods")
    ], ["product_name", "price", "category"]

# Example database schema for test mode
example_db_schema = r'''{
    'Company':
      CREATE TABLE EMPLOYEES (
    EMPLOYEE_ID    NUMBER(6) PRIMARY KEY,
    FIRST_NAME_EN  VARCHAR2(20),
    SECOND_NAME_EN VARCHAR2(20),
    THIRD_NAME_EN  VARCHAR2(20),
    LAST_NAME_EN   VARCHAR2(20),
    FIRST_NAME_AR  NVARCHAR2(20),
    SECOND_NAME_AR NVARCHAR2(20),
    THIRD_NAME_AR  NVARCHAR2(20),
    LAST_NAME_AR   NVARCHAR2(20),
    EMAIL          VARCHAR2(50),
    PHONE_NUMBER   VARCHAR2(20),
    HIRE_DATE      DATE,
    JOB_ID         VARCHAR2(10),
    SALARY         NUMBER(8,2),
    MANAGER_ID     NUMBER(6),
    DEPARTMENT_ID  NUMBER(4)
          Answer the following questions about this schema:
}'''

# Main function
def main():
    # Initialize models
    transcriber, sql_model, tokenizer, tts_processor, tts_model = initialize_models()

    # Try to connect to database using environment variables
    db_connection = connect_to_db()

    # Set test mode flag and get schema
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
            # Ask if user wants to use voice or text input
            print("Do you want to use voice input (v) or text input (t)?")
            input_mode = input().lower()

            if input_mode == 'v':
                # Record audio
                audio_file = record_audio()

                # Transcribe audio to text
                arabic_text = transcribe_audio(transcriber, audio_file)
                print(f"Transcribed text: {arabic_text}")
            else:
                # Get text input directly
                print("Enter your question in Arabic:")
                arabic_text = input()
                print(f"Text input: {arabic_text}")

            # Convert to SQL using the new method
            sql_query = text_to_sql(sql_model, tokenizer, arabic_text, db_schema)
            print(f"Generated SQL: {sql_query}")

            # Execute query or use test mode
            if test_mode:
                results, column_names = test_mode_query(sql_query)
            else:
                results, column_names = execute_query(db_connection, sql_query)

            # Format response
            response = format_response(results, column_names)
            print(f"Response: {response}")

            # Ask if user wants to hear the response
            print("Do you want to hear the response? (y/n)")
            if input().lower() == 'y':
                if tts_processor is not None and tts_model is not None:
                    generate_speech_with_local_model(tts_processor, tts_model, response)
                else:
                    print("Error: TTS model not available")

        except Exception as e:
            print(f"Error occurred: {e}")
            response = "عذراً، حدث خطأ أثناء معالجة طلبك."
            print(response)

        # Ask if user wants to continue
        print("Do you want to ask another question? (y/n)")
        if input().lower() != 'y':
            break

    if not test_mode:
        db_connection.close()

if __name__ == "__main__":
    main()




