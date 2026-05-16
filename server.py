from fastapi import FastAPI
from db_manager import get_summary, init_db
import uvicorn

app = FastAPI(title="Log Analyzer API")

@app.on_event("startup")
def startup_event():
    init_db()

@app.get("/summary")
def read_summary():
    """
    Returns a summary of log classifications.
    """
    summary = get_summary()
    return {
        "status": "success",
        "data": summary
    }

@app.get("/")
def read_root():
    return {"message": "Welcome to the Log Analyzer API. Use /summary to see results."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
