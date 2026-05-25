# Unit Tests Documentation

This project uses standard-library `unittest` tests to validate the core application behavior without needing Groq or Langfuse to be available.

## Test Scope

### `tests/test_agent.py`
- Verifies `parse_log_line()` accepts the expected log format.
- Verifies `parse_log_line()` rejects malformed input.
- Verifies `process_file_sync()` can ingest a small log file, classify anomalies, aggregate stats, and produce an RCA report in offline fallback mode.

### `tests/test_server.py`
- Verifies `/health` returns the expected status payload.
- Verifies `POST /logs/report/{job_id}` stores and returns a report.
- Verifies `GET /logs/report/{job_id}` and `GET /logs/status/{job_id}` read back persisted state.
- Verifies `/summary` returns the SQLite summary payload.
- Verifies `POST /logs/upload` accepts a file upload and registers a job.

## How To Run

Run all tests from the project root:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

Run a single file:

```powershell
python -m unittest tests.test_agent
python -m unittest tests.test_server
```

## Expected Behavior

- Tests should run offline.
- No external Groq API key is required for the unit tests.
- No Langfuse account is required for the unit tests.

## What The Tests Do Not Cover

- They do not validate live Groq model quality.
- They do not validate Langfuse trace delivery end-to-end.
- They do not run a real Kubernetes deployment.