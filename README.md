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
- **Web Interface:** Simple Flask-based web UI for interaction.
- **Modular Codebase:** Easy to extend and maintain.
- **Integration with LM Studio:** You need to have [LM Studio](https://lmstudio.ai/) installed and running locally to enable advanced language model features.

---

## Project Structure
```
app.py                    # Main Flask application (web server)
arabic_voice_assistant.py # Orchestrator/facade for assistant workflows
speech.py                 # Audio recording and transcription helpers
sql_engine.py             # LM Studio text-to-SQL generation logic
database.py               # Database connection, schema loading, query execution
tts_engine.py             # Arabic text-to-speech model helpers
response_formatter.py     # Arabic response formatting utilities

templates/
  index.html              # Main web interface template
  package.json            # (If used for frontend dependencies)

README.md                 # Project documentation
requirements.txt          # Python dependencies (create if missing)
```

---

## Requirements
- Python 3.12+
- MySQL Server (local or remote)
- [LM Studio](https://lmstudio.ai/) (for local language model inference)
- Recommended: Virtual environment for Python

### Python Packages
- Flask
- mysql-connector-python
- sounddevice (for microphone input)
- soundfile
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
   pip install -r requirements.txt
   ```

4. **Set up MySQL database:**
   - Ensure MySQL is running.
   - Create a database named `arabic_voice_assistant_db` (or update `.env` for a different name).

5. **Install and run LM Studio:**
   - Download and install LM Studio from [https://lmstudio.ai/](https://lmstudio.ai/).
   - Launch LM Studio and ensure your desired language model is running locally.

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
FAL_AI_API_KEY=your_fal_ai_api_key_here
LM_STUDIO_BASE_URL=http://127.0.0.1:1234
FLASK_HOST=127.0.0.1
FLASK_PORT=5000
FLASK_DEBUG=false
```

- Replace `your_password` with your MySQL password.
- Replace `your_fal_ai_api_key_here` with your FAL AI API key if you use the FAL AI provider for speech recognition.
- Set `LM_STUDIO_BASE_URL` to your LM Studio server URL if different from the default.
- Never commit your `.env` file to version control.
- You can copy `.env.example` to `.env` and then edit values.

---

## Query Safety
- The app only allows read-only SQL (`SELECT` / `WITH ... SELECT`).
- Write and schema-changing SQL statements are blocked before execution.
- Use a read-only MySQL user in `.env` for additional safety.

---

## Usage
1. **Start LM Studio and load your preferred language model.**
2. **Start the application:**
   ```pwsh
   python app.py
   ```
3. **Open your browser:**
   - Go to [http://localhost:5000](http://localhost:5000) (or the port specified in your app).
4. **Interact with the assistant:**
   - Use the web interface to send voice/text commands and receive responses.

---

## Troubleshooting
- **MySQL connection errors:**
  - Check your credentials and database name in the `.env` file.
  - Ensure MySQL server is running and accessible.
- **Missing dependencies:**
  - Run `pip install -r requirements.txt` again.

---
