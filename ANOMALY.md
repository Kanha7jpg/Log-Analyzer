# Log Anomaly Detection

This project uses Groq SLM via a classification step in `agent.py` to label log messages as NORMAL, WARNING, or CRITICAL. The classification output is stored in the database and exposed via the API.

Notes:
- Classification is performed in `classify_logs_node` in `agent.py`.
- Ensure `GROQ_API_KEY` is set in your environment for Groq access.
- For production, consider structured JSON outputs from the model and batching with retries.
