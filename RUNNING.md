# Running the Project

## 1) Start MySQL
- Ensure MySQL service is running.
- Windows example (service name may vary):

```pwsh
Get-Service *mysql*
Start-Service MySQL97
```

## 2) Start Ollama

```pwsh
ollama serve
```

In another terminal, confirm your model exists:

```pwsh
ollama list
```

## 3) Set Up Python Environment
From project root, create and activate a virtual environment, then install dependencies:

```pwsh
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

> Re-run `pip install -r backend/requirements.txt` whenever dependencies change. Activation (`.venv\Scripts\Activate.ps1`) is required in every new terminal session.

## 4) Start Backend (FastAPI)
From project root (with venv active):

```pwsh
python backend/prestart_model_check.py --allow-download
python backend/main.py
```

Alternative command:

```pwsh
uvicorn main:app --app-dir backend --host 127.0.0.1 --port 5000
```

## 5) Open the app
- http://127.0.0.1:5000

## Notes
- Configure values in `.env` before first run (`DB_*`, `OLLAMA_*`, `ASR_*`, and limits).
- Use `python backend/prestart_model_check.py` (without `--allow-download`) when you want strict local-cache validation only.
