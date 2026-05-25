# Log Analyzer

Log Analyzer ingests application logs, classifies anomalies, generates a root-cause-analysis report, stores the result, and publishes the report to a REST endpoint. The app is available as a FastAPI service and can also run as a local LangGraph pipeline.

## Architecture


flowchart LR
    A[app.log / uploaded log file] --> B[Ingest logs]
    B --> C[Classify anomalies]
    C --> D[Aggregate stats]
    D --> E[Generate RCA report]
    E --> F[Persist report]
    F --> G[POST /logs/report/{job_id}]
    B -. trace .-> H[Langfuse]
    C -. trace .-> H
    D -. trace .-> H
    E -. trace .-> H
    F -. trace .-> H


## Project Layout

- `agent.py` orchestrates the LangGraph workflow.
- `server.py` exposes the FastAPI endpoints.
- `db_manager.py` handles SQLite storage for parsed log entries.
- `generate_synthetic_log.py` creates a synthetic `app.log` for testing.
- `tests/` contains unit tests for the workflow and API layer.

## How To Run

### 1. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Generate a synthetic log file

```powershell
python generate_synthetic_log.py 500
```

### 4. Run the API server

```powershell
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

### 5. Run the pipeline locally

```powershell
$env:LOG_ANALYZER_API_URL='http://127.0.0.1:8000'
python -c "from agent import process_file_sync; process_file_sync('app.log', persist=True)"
```

### 6. Check the results

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/health -UseBasicParsing | Select-Object -ExpandProperty Content
Invoke-WebRequest -Uri http://127.0.0.1:8000/summary -UseBasicParsing | Select-Object -ExpandProperty Content
```

## Unit Tests

Run the full unit test suite with:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

## Notes

- The workflow uses Groq and Langfuse when those services are configured.
- For local development, the pipeline falls back to deterministic classification and RCA generation so you can still exercise the full flow offline.
# Log Analyzer

Log Analyzer ingests application logs, classifies anomalies, generates a root-cause-analysis report, stores the result, and publishes the report to a REST endpoint. The app is available as a FastAPI service and can also run as a local LangGraph pipeline.

## Architecture


flowchart LR
    A[app.log / uploaded log file] --> B[Ingest logs]
    B --> C[Classify anomalies]
    C --> D[Aggregate stats]
    D --> E[Generate RCA report]
    E --> F[Persist report]
    F --> G[POST /logs/report/{job_id}]
    B -. trace .-> H[Langfuse]
    C -. trace .-> H
    D -. trace .-> H
    E -. trace .-> H
    F -. trace .-> H


## Project Layout

- `agent.py` orchestrates the LangGraph workflow.
- `server.py` exposes the FastAPI endpoints.
- `db_manager.py` handles SQLite storage for parsed log entries.
- `generate_synthetic_log.py` creates a synthetic `app.log` for testing.
- `tests/` contains unit tests for the workflow and API layer.

## How To Run

### 1. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Generate a synthetic log file

```powershell
python generate_synthetic_log.py 500
```

### 4. Run the API server

```powershell
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

### 5. Run the pipeline locally

```powershell
$env:LOG_ANALYZER_API_URL='http://127.0.0.1:8000'
python -c "from agent import process_file_sync; process_file_sync('app.log', persist=True)"
```

### 6. Check the results

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/health -UseBasicParsing | Select-Object -ExpandProperty Content
Invoke-WebRequest -Uri http://127.0.0.1:8000/summary -UseBasicParsing | Select-Object -ExpandProperty Content
```

## Unit Tests

Run the full unit test suite with:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

## Notes

- The workflow uses Groq and Langfuse when those services are configured.
- For local development, the pipeline falls back to deterministic classification and RCA generation so you can still exercise the full flow offline.