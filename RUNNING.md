# Running the Project

## 1) Start MySQL
- Ensure MySQL service is running.
- Windows example (service name may vary):

```pwsh
Get-Service *mysql*
Start-Service MySQL80
```

## 2) Start Ollama

```pwsh
ollama serve
```

In another terminal, confirm your model exists:

```pwsh
ollama list
```

## 3) Start Backend (FastAPI)
From project root:

```pwsh
python backend/prestart_model_check.py --allow-download
python backend/main.py
```

Alternative command:

```pwsh
uvicorn backend.main:app --host 127.0.0.1 --port 5000
```

## 4) Open the app
- http://127.0.0.1:5000

## Notes
- Configure values in `.env` before first run (`DB_*`, `OLLAMA_*`, `ASR_*`, and limits).
- Use `python backend/prestart_model_check.py` (without `--allow-download`) when you want strict local-cache validation only.
