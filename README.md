# Arabic Speech-to-SQL Voice Assistant

An open-source Arabic Voice Assistant built with Python and MySQL, featuring voice recognition, database integration, and a web interface. This project demonstrates how to process Arabic speech, store and retrieve data, and interact with users through a simple web app.

**This project is designed to convert Arabic speech into SQL commands and execute them on a MySQL database.**

---

## Table of Contents
- [Features](#features)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Environment Variables Setup](#environment-variables-setup)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)


---

## Features
- **Arabic Speech Recognition:** Converts spoken Arabic to text using Python libraries.
- **MySQL Database Integration:** Stores and retrieves user data and assistant responses.
- **Web Interface:** FastAPI-based backend serving a simple web UI for interaction.
- **Modular Codebase:** Easy to extend and maintain.
- **Integration with Ollama:** You need to have [Ollama](https://ollama.com/) installed and running locally to enable text-to-SQL generation.
- **Local ASR with faster-whisper:** Uses `large-v3-turbo` with INT8 compute for fast Arabic transcription on GPU.

---

## Project Structure
```
backend/
   main.py                   # Main FastAPI application (web server)
   arabic_voice_assistant.py # Orchestrator/facade for assistant workflows
   speech.py                 # Audio recording and transcription helpers
   sql_engine.py             # Ollama text-to-SQL generation logic
   database.py               # Database connection, schema loading, query execution
   tts_engine.py             # Arabic text-to-speech model helpers
   response_formatter.py     # Arabic response formatting utilities
   requirements.txt          # Python dependencies

frontend/
  index.html              # Main web interface template
   package.json            # Frontend dependencies

README.md                 # Project documentation
.env.example              # Environment template
```

---

## Requirements
- Python 3.12+
- MySQL Server (local or remote)
- [Ollama](https://ollama.com/) (for local language model inference)
- Internet connection on first run to download Supertonic-3 model assets
- Recommended: Virtual environment for Python

### Python Packages
- fastapi
- uvicorn
- mysql-connector-python
- sounddevice (for microphone input)
- soundfile
- faster-whisper
- supertonic
- sqlglot
- Any other dependencies listed in `requirements.txt`

---

## Installation
1. **Clone the repository:**
   ```pwsh
   git clone <https://github.com/Mostafa-Emad77/Arabic-Speech-to-SQL-Voice-Assistant>
   cd Arabic-Speech-to-SQL-Voice-Assistant
   ```
2. **Set up a virtual environment (optional but recommended):**
   ```pwsh
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
3. **Install dependencies:**
   ```pwsh
   pip install -r backend/requirements.txt
   ```

4. **Set up MySQL database:**
   - Ensure MySQL is running.
   - Create a database named `arabic_voice_assistant_db` (or update `.env` for a different name).

5. **Install and run Ollama:**
   - Download and install Ollama from [https://ollama.com/](https://ollama.com/).
   - Pull a model (example): `ollama pull llama3.1:8b`
   - Start Ollama service and ensure it is running on port `11434`.

---

## Configuration
- Make sure the user has privileges to access the database.

---

## Environment Variables Setup
Sensitive information such as database credentials and API keys should be stored in a `.env` file in the project root. Create a `.env` file with the following content:

```
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=arabic_voice_assistant_db
ASR_MODEL=large-v3-turbo
ASR_DEVICE=cuda
ASR_COMPUTE_TYPE=int8_float16
ASR_BEAM_SIZE=5
MAX_PROMPT_CHARS=1200
SQL_MAX_RETRIES=2
SQL_MAX_RESULT_ROWS=200
SQL_MAX_EXPORT_ROWS=20000
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_THINK=false
TTS_LANG=ar
TTS_VOICE=M1
TTS_AUTO_DOWNLOAD=true
FASTAPI_HOST=127.0.0.1
FASTAPI_PORT=5000
FLASK_DEBUG=false
```

- Replace `your_password` with your MySQL password.
- `ASR_MODEL` defaults to `large-v3-turbo`.
- `ASR_DEVICE` defaults to `cuda` (change to `cpu` if needed).
- `ASR_COMPUTE_TYPE` defaults to `int8_float16` for a strong speed/VRAM tradeoff.
- `ASR_BEAM_SIZE` controls decoding quality/speed (default `5`).
- `MAX_PROMPT_CHARS` limits prompt length before SQL generation.
- `SQL_MAX_RETRIES` reserves retry budget for SQL correction loops.
- `SQL_MAX_RESULT_ROWS` applies a hard cap on returned rows per query.
- `SQL_MAX_EXPORT_ROWS` caps CSV export row count to keep export operations bounded.
- Set `OLLAMA_BASE_URL` to your Ollama server URL if different from the default.
- Set `OLLAMA_MODEL` to the local model tag you pulled in Ollama.
- Set `OLLAMA_THINK=false` to disable model thinking (faster responses on thinking-capable models).
- Set `TTS_LANG` to target language (`ar` for Arabic).
- Set `TTS_VOICE` to a Supertonic preset voice (default `M1`).
- Set `TTS_AUTO_DOWNLOAD=true` to allow automatic model download on first run.
- Never commit your `.env` file to version control.
- You can copy `.env.example` to `.env` and then edit values.

---

## Query Safety
- The app only allows read-only SQL (`SELECT` / `WITH ... SELECT`).
- Write and schema-changing SQL statements are blocked before execution.
- Use a read-only MySQL user in `.env` for additional safety.

---

## Usage
1. **Start Ollama and make sure your configured model is available locally.**
2. **Run model prestart checks (ASR + TTS):**
   ```pwsh
   python backend/prestart_model_check.py --allow-download
   ```
3. **Start the application:**
   ```pwsh
   python backend/main.py
   ```
4. **Open your browser:**
   - Go to [http://localhost:5000](http://localhost:5000) (or the port specified in your app).
5. **Interact with the assistant:**
   - Use the web interface to send voice/text commands and receive responses.

---

## Troubleshooting
- **MySQL connection errors:**
  - Check your credentials and database name in the `.env` file.
  - Ensure MySQL server is running and accessible.
- **Missing dependencies:**
   - Run `pip install -r backend/requirements.txt` again.

---
