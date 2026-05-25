import json
import os
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, BackgroundTasks
from pydantic import BaseModel

from db_manager import get_summary, init_db
import uvicorn

app = FastAPI(title="Log Analyzer API")
REPORTS_DIR = "reports"
REPORTS_INDEX = {}
UPLOADS_DIR = "uploads"
UPLOADS_INDEX = {}


class ReportPayload(BaseModel):
    job_id: str
    stats: dict
    rca_report: dict
    job_status: str = "completed"


def report_path(job_id: str) -> str:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    return os.path.join(REPORTS_DIR, f"rca_{job_id}.json")


def upload_path(job_id: str) -> str:
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    return os.path.join(UPLOADS_DIR, f"{job_id}.log")


def _start_job_background(job_id: str, file_path: str) -> None:
    # Run agent pipeline in background and update reports index when done
    try:
        from agent import run_job

        run_job(file_path, job_id)
        # if run_job posts back to /logs/report the REPORTS_INDEX will be updated by that POST
        # otherwise try to load the generated report file
        rp = report_path(job_id)
        if os.path.exists(rp):
            with open(rp, "r", encoding="utf-8") as f:
                record = json.load(f)
                REPORTS_INDEX[job_id] = record
    except Exception as e:
        REPORTS_INDEX[job_id] = {"job_id": job_id, "job_status": "failed", "error": str(e)}


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


@app.post("/logs/upload", status_code=202)
async def upload_log(file: UploadFile, background_tasks: BackgroundTasks):
    """Upload a raw app.log file. Triggers ingestion pipeline and returns a job_id (202 Accepted)."""
    job_id = str(uuid.uuid4())
    path = upload_path(job_id)
    contents = await file.read()
    with open(path, "wb") as f:
        f.write(contents)

    UPLOADS_INDEX[job_id] = {"file_path": path, "job_status": "uploaded"}
    # start pipeline in background
    background_tasks.add_task(_start_job_background, job_id, path)

    return {"status": "accepted", "job_id": job_id}


@app.get("/logs/analyze/{job_id}")
def analyze_logs(job_id: str):
    """Trigger Groq-based anomaly classification for the ingested log job and return classified entries."""
    upload = UPLOADS_INDEX.get(job_id)
    if not upload:
        # check if a report exists; if so, return its classified logs if present
        rpt = REPORTS_INDEX.get(job_id)
        if rpt:
            return {"status": "success", "data": rpt.get("classified_logs", [])}
        raise HTTPException(status_code=404, detail="job_id not found")

    file_path = upload["file_path"]
    try:
        from agent import process_file_sync

        state = process_file_sync(file_path, job_id=job_id, persist=False)
        # update status
        upload["job_status"] = "analyzed"
        return {"status": "success", "data": state.get("classified_logs", [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/logs/summary/{job_id}")
def job_summary(job_id: str):
    """Return an aggregated summary for the given job_id (total lines, error count, warning count, top repeated errors)."""
    # prefer persisted report
    rpt = REPORTS_INDEX.get(job_id)
    if rpt:
        return {"status": "success", "data": rpt.get("stats", {})}

    upload = UPLOADS_INDEX.get(job_id)
    if not upload:
        raise HTTPException(status_code=404, detail="job_id not found")

    file_path = upload["file_path"]
    try:
        from agent import process_file_sync

        state = process_file_sync(file_path, job_id=job_id, persist=False)
        return {"status": "success", "data": state.get("stats", {})}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok", "service": "log-analyzer", "version": "1.0.0"}

@app.get("/")
def read_root():
    return {"message": "Welcome to the Log Analyzer API. Use /summary, /logs/report/{job_id}, and /logs/status/{job_id}."}


@app.post("/logs/report/{job_id}")
def upsert_report(job_id: str, payload: ReportPayload):
    if job_id != payload.job_id:
        raise HTTPException(status_code=400, detail="job_id in path and body must match")

    record = {
        "job_id": payload.job_id,
        "job_status": payload.job_status,
        "stats": payload.stats,
        "rca_report": payload.rca_report,
    }

    REPORTS_INDEX[job_id] = record
    with open(report_path(job_id), "w", encoding="utf-8") as file:
        json.dump(record, file, indent=2)

    return {"status": "success", "data": record}


@app.get("/logs/report/{job_id}")
def get_report(job_id: str):
    record = REPORTS_INDEX.get(job_id)
    if record is None:
        file_path = report_path(job_id)
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as file:
                record = json.load(file)

    if record is None:
        raise HTTPException(status_code=404, detail="report not found")

    return {"status": "success", "data": record}


@app.get("/logs/status/{job_id}")
def get_job_status(job_id: str):
    record = REPORTS_INDEX.get(job_id)
    if record is None:
        file_path = report_path(job_id)
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as file:
                record = json.load(file)

    if record is None:
        raise HTTPException(status_code=404, detail="job not found")

    return {"status": "success", "data": {"job_id": job_id, "job_status": record.get("job_status", "unknown")}}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
