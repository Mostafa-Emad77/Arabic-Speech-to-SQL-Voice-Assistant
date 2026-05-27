# Arabic Speech-to-SQL Voice Assistant (فَهِيم)

An open-source Arabic Voice Assistant that converts spoken Arabic into SQL queries and executes them on a MySQL database. Ask a question in Arabic — by voice or text — and get results read back to you in natural Arabic.

---

## Table of Contents
- [Features](#features)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Environment Variables](#environment-variables)
- [Usage](#usage)
- [Upload Your Own Data](#upload-your-own-data)
- [Arabic Output Formatting](#arabic-output-formatting)
- [Query Safety & Security](#query-safety--security)
- [Troubleshooting](#troubleshooting)

---

## Features

### Core
- **Arabic Speech Recognition** — Converts spoken Arabic to text using `faster-whisper` (`large-v3-turbo` model with INT8 compute for fast GPU transcription).
- **Text-to-SQL via LLM** — Translates Arabic questions into SQL using a local Ollama model (e.g., `qwen3.5:4b`, `llama3.1:8b`).
- **Arabic Text-to-Speech** — Reads results aloud using the Supertonic TTS engine.
- **MySQL Database Integration** — Queries any MySQL database and returns structured results.

### Smart Query Generation
- **SQL Retry on Failure** — If a generated SQL query fails validation or execution, the error is fed back to the LLM for a corrected query (configurable retries).
- **Empty-Result Retry** — If a valid query returns zero rows, the LLM is asked to generate a better query.
- **Style-Constrained Prompts** — The LLM prompt includes SQL best-practice rules: prefer `ORDER BY + LIMIT` over nested subqueries, require `GROUP BY` with aggregates, etc.

### Arabic-First Output
- **Column Name Translation** — English column names (e.g., `salary`, `department_name`) are automatically translated to Arabic labels (الراتب، القسم).
- **Numbers as Arabic Words** — Numeric values are converted to Arabic words using `num2words` for TTS-friendly output (e.g., `5000` → `خمسة آلاف`).
- **Arabic Date Formatting** — Dates are formatted as `١٠ يونيو ٢٠٢٤` instead of `2024-06-10`.
- **Aggregate Function Labels** — `COUNT(*)`, `AVG(salary)`, etc. are rendered as عدد، متوسط الراتب.

### Dynamic Data Upload
- **CSV/Excel Upload** — Upload your own `.csv` or `.xlsx` files through the web UI. The app auto-creates a temporary MySQL database with inferred schema.
- **Demo Data Fallback** — A built-in demo dataset is always available; switch back with one click.
- **Auto Cleanup** — Temporary databases are dropped on app shutdown or when new data is uploaded.

### Security
- **Read-Only SQL Enforcement** — Only `SELECT` statements are allowed; `INSERT`, `UPDATE`, `DELETE`, `DROP`, etc. are blocked via regex + AST parsing (`sqlglot`).
- **Prompt Injection Defense** — User prompts are sanitized and checked against blocked patterns (e.g., "ignore system instructions").
- **Input Validation** — Prompt length limits, file size limits (10 MB/file, 50 MB total, max 10 files), and sanitized table/column names.

### Frontend
- **Modern RTL Web UI** — Responsive Arabic-first interface with voice recording, text input, and result display.
- **Voice Recording** — Press-to-record mic with live timer, audio-reactive visualizer bars, and auto-send on stop.
- **Suggestion Chips** — Pre-built example queries to try immediately.
- **CSV Export** — Download query results as a CSV file.
- **TTS Playback** — Listen to results with one click.

---

## Project Structure
```
backend/
  main.py                    # FastAPI app — endpoints, lifespan, routing
  arabic_voice_assistant.py  # Orchestrator/facade for all assistant workflows
  speech.py                  # Audio recording and faster-whisper transcription
  sql_engine.py              # Ollama text-to-SQL with prompt engineering
  database.py                # DB connection, schema loading, query execution, SQL validation
  data_upload.py             # CSV/Excel upload → dynamic MySQL database creation
  response_formatter.py      # Arabic response formatting (numbers, dates, columns)
  tts_engine.py              # Supertonic Arabic text-to-speech
  security.py                # Prompt sanitization, validation, security config
  prestart_model_check.py    # Pre-flight check for ASR + TTS models
  requirements.txt           # Python dependencies
  tests/                     # Unit tests (pytest)

frontend/
  index.html                 # Main HTML — voice UI, text input, upload modal
  styles.css                 # Full CSS — RTL layout, modal, components
  app.js                     # Client JS — recording, upload, TTS, state management

README.md
.env.example
```

---

## Requirements
- **Python 3.12+**
- **MySQL Server** (local or remote)
- **[Ollama](https://ollama.com/)** (local LLM inference)
- **GPU recommended** for faster-whisper ASR (falls back to CPU)
- Internet connection on first run to download Supertonic TTS model assets

### Python Packages
All dependencies are in `backend/requirements.txt`:
- `fastapi`, `uvicorn` — Web server
- `mysql-connector-python` — Database driver
- `faster-whisper` — Arabic ASR
- `supertonic` — Arabic TTS
- `sqlglot` — SQL parsing and validation
- `num2words` — Number-to-Arabic-words conversion
- `pandas`, `openpyxl` — CSV/Excel file parsing for data upload
- `python-dotenv` — Environment variable management
- `sounddevice`, `soundfile` — Audio I/O

---

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Mostafa-Emad77/Arabic-Speech-to-SQL-Voice-Assistant
   cd Arabic-Speech-to-SQL-Voice-Assistant
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   # Windows PowerShell
   .\.venv\Scripts\Activate.ps1
   # Linux/macOS
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r backend/requirements.txt
   ```

4. **Set up MySQL:**
   - Ensure MySQL is running.
   - Create a database: `CREATE DATABASE arabic_voice_assistant_db;`
   - For data upload feature, the MySQL user needs `CREATE DATABASE` and `DROP DATABASE` privileges.

5. **Install and run Ollama:**
   - Download from [https://ollama.com/](https://ollama.com/)
   - Pull a model: `ollama pull qwen3.5:4b` (or any model of your choice)
   - Ensure Ollama is running on port `11434`

6. **Copy environment template:**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

---

## Configuration

### Environment Variables
Create a `.env` file in the project root:

```env
# ── Database ──
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=arabic_voice_assistant_db

# ── ASR (Speech Recognition) ──
ASR_MODEL=large-v3-turbo
ASR_DEVICE=cuda              # or "cpu"
ASR_COMPUTE_TYPE=int8_float16
ASR_BEAM_SIZE=5

# ── LLM (Ollama) ──
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:4b
OLLAMA_THINK=false

# ── TTS (Text-to-Speech) ──
TTS_LANG=ar
TTS_VOICE=M1
TTS_AUTO_DOWNLOAD=true

# ── Security & Limits ──
MAX_PROMPT_CHARS=1200
SQL_MAX_RETRIES=2
SQL_MAX_RESULT_ROWS=200
SQL_MAX_EXPORT_ROWS=20000

# ── Server ──
FASTAPI_HOST=127.0.0.1
FASTAPI_PORT=5000
DEBUG=false
```

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | `localhost` | MySQL server hostname |
| `DB_USER` | `root` | MySQL username |
| `DB_PASSWORD` | — | MySQL password |
| `DB_NAME` | — | Default database name |
| `ASR_MODEL` | `large-v3-turbo` | faster-whisper model variant |
| `ASR_DEVICE` | `cuda` | `cuda` for GPU, `cpu` for CPU |
| `ASR_COMPUTE_TYPE` | `int8_float16` | Quantization type for speed/VRAM tradeoff |
| `ASR_BEAM_SIZE` | `5` | Beam search width (higher = more accurate, slower) |
| `OLLAMA_MODEL` | `llama3.1:8b` | Ollama model tag for text-to-SQL |
| `OLLAMA_THINK` | `false` | Enable/disable model thinking mode |
| `SQL_MAX_RETRIES` | `2` | Max LLM retry attempts on failed/empty queries |
| `SQL_MAX_RESULT_ROWS` | `200` | Max rows returned per query |
| `SQL_MAX_EXPORT_ROWS` | `20000` | Max rows in CSV export |
| `MAX_PROMPT_CHARS` | `1200` | Max characters in user prompt |
| `TTS_VOICE` | `M1` | Supertonic voice preset |

> **Never commit your `.env` file to version control.**

---

## Usage

1. **Start Ollama** and ensure your model is available.

2. **Run model prestart checks:**
   ```bash
   python backend/prestart_model_check.py --allow-download
   ```

3. **Start the server:**
   ```bash
   cd backend
   uvicorn main:app --host 127.0.0.1 --port 5000
   ```
   Or:
   ```bash
   python backend/main.py
   ```

4. **Open** [http://localhost:5000](http://localhost:5000) in your browser.

5. **Interact:**
   - Press the mic button and ask your question in Arabic
   - Or use the text input to type your question
   - Click suggestion chips to try example queries
   - Listen to results via the TTS playback button
   - Export results as CSV

---

## Upload Your Own Data

You can upload your own CSV or Excel files instead of using the built-in demo database:

1. Click the **"بيانات تجريبية"** button in the top bar.
2. Drag and drop files (`.csv`, `.xlsx`) into the upload zone, or click to browse.
3. Click **"رفع البيانات"** to upload. The app will:
   - Parse each file and infer column types (INT, DECIMAL, VARCHAR, DATE, etc.)
   - Create a temporary MySQL database with a table per file
   - Switch all queries to use the new database
4. Ask questions about your uploaded data via voice or text.
5. Click **"الرجوع للتجريبية"** to switch back to the demo dataset.

### Limits
- Max **10 files** per upload
- Max **10 MB** per file, **50 MB** total
- Supported formats: `.csv`, `.xlsx`, `.xls`
- MySQL user must have `CREATE DATABASE` / `DROP DATABASE` privileges
- Temporary databases are auto-cleaned on shutdown

---

## Arabic Output Formatting

All query results are formatted for Arabic TTS consumption:

| Feature | Example |
|---------|---------|
| Column labels | `salary` → الراتب |
| Numbers as words | `5000` → خمسة آلاف |
| Dates | `2024-06-10` → ١٠ يونيو ٢٠٢٤ |
| Aggregates | `AVG(salary)` → متوسط الراتب |
| Null values | `NULL` → غير محدد |
| Overflow notice | "تم عرض أول مئتا صف" |

---

## Query Safety & Security

- **Read-only enforcement** — Only `SELECT` / `WITH ... SELECT` queries are allowed. All DML/DDL is blocked via regex keyword matching + `sqlglot` AST validation.
- **Prompt injection defense** — Blocked patterns include: "ignore system instructions", "bypass policy", "reveal prompt", SQL keywords in user text.
- **Input sanitization** — Control characters stripped, whitespace normalized, length enforced.
- **File upload safety** — Table/column names are sanitized to prevent SQL injection. Size limits enforced.
- **Recommendation** — Use a read-only MySQL user in `.env` for defense-in-depth.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serve the web UI |
| `POST` | `/process_audio` | Process voice recording → SQL → results |
| `POST` | `/process_text` | Process text question → SQL → results |
| `POST` | `/text_to_speech` | Convert text to Arabic speech audio |
| `POST` | `/export_csv` | Export query results as CSV |
| `GET` | `/data_status` | Get current data source info |
| `POST` | `/upload_data` | Upload CSV/Excel files to create a new database |
| `POST` | `/reset_data` | Reset to demo database |

---

## Running Tests

```bash
python -m pytest backend/tests/ -v --tb=short
```

---

## Troubleshooting

- **MySQL connection errors:**
  - Check credentials in `.env`
  - Ensure MySQL server is running
  - For data upload: verify the user has `CREATE DATABASE` privileges

- **Ollama not responding:**
  - Ensure Ollama is running: `ollama list`
  - Check `OLLAMA_BASE_URL` matches the Ollama server address

- **ASR model download fails:**
  - Run `python backend/prestart_model_check.py --allow-download` with internet access
  - Check disk space for model files

- **TTS not working:**
  - Ensure `TTS_AUTO_DOWNLOAD=true` on first run
  - Check that Supertonic model files were downloaded successfully

- **Empty results from queries:**
  - The app retries automatically (up to `SQL_MAX_RETRIES`)
  - Try rephrasing your question more specifically

- **Missing dependencies:**
  - `pip install -r backend/requirements.txt`

---
