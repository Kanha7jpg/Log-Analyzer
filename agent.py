import re
import os
import json
import uuid
from typing import TypedDict, List, Dict
from dotenv import load_dotenv

# Langfuse is optional for local runs. Provide no-op fallbacks when unavailable.
try:
    from langfuse import observe, get_client
    from langfuse.langchain import CallbackHandler
except Exception:
    # Define a simple no-op observe decorator and client for local testing
    def observe(name=None, as_type=None, capture_input=True, capture_output=True):
        def _decorator(fn):
            return fn
        return _decorator

    class _NoopClient:
        def update_current_span(self, *args, **kwargs):
            return None

    def get_client():
        return _NoopClient()

    class CallbackHandler:
        def __init__(self):
            pass
from langgraph.graph import StateGraph, END
import requests

# Load environment variables
load_dotenv()
from db_manager import init_db, save_logs

# Define the state
class AgentState(TypedDict):
    log_file_path: str
    lines: List[str]
    parsed_logs: List[Dict]
    classified_logs: List[Dict]
    stats: Dict
    rca_report: Dict
    job_status: str
    total_count: int
    job_id: str

# Regex for parsing: "2026-05-13 12:00:01 INFO [AuthService] User logged in"
LOG_PATTERN = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) \[(\w+)\] (.*)$')

def parse_log_line(line: str):
    match = LOG_PATTERN.match(line)
    if not match:
        return None

    timestamp, level, service, message = match.groups()
    return {
        "timestamp": timestamp,
        "level": level,
        "service": service,
        "message": message,
    }

def _langfuse_handler() -> CallbackHandler:
    return CallbackHandler()

@observe(name="ingest_logs", as_type="span", capture_input=False, capture_output=False)
def read_logs_node(state: AgentState) -> AgentState:
    print("--- ingest_logs ---")
    path = state["log_file_path"]
    if not os.path.exists(path):
        print(f"Error: {path} not found.")
        get_client().update_current_span(metadata={"log_file_path": path, "found": False})
        return {**state, "lines": []}
    
    with open(path, "r") as f:
        lines = [line.strip() for line in f if line.strip()]
    
    parsed_logs = []
    for line in lines:
        parsed_log = parse_log_line(line)
        if parsed_log:
            parsed_logs.append(parsed_log)
        else:
            print(f"Skipping malformed line: {line}")

    get_client().update_current_span(
        metadata={
            "log_file_path": path,
            "found": True,
            "line_count": len(lines),
            "parsed_count": len(parsed_logs),
        }
    )

    return {**state, "lines": lines, "parsed_logs": parsed_logs, "total_count": len(lines)}

@observe(name="classify_anomalies", as_type="span", capture_input=False, capture_output=False)
def classify_anomalies_node(state: AgentState) -> AgentState:
    print("--- classify_anomalies ---")
    # Prefer using Groq when a valid key is configured; otherwise fall back
    # to a lightweight deterministic classifier so the pipeline can run offline.

    if not state["parsed_logs"]:
        return state

    api_key = os.getenv("GROQ_API_KEY")
    classified_logs = []

    if api_key:
        try:
            # Lazy import langchain-backed Groq LLM only when needed
            from langchain_groq import ChatGroq
            from langchain_core.prompts import ChatPromptTemplate
            from groq import Groq

            Groq(api_key=api_key).models.list()

            # Batch processing
            batch_text = "\n".join([f"{i}: {log['message']}" for i, log in enumerate(state["parsed_logs"])])

            prompt = ChatPromptTemplate.from_messages([
                ("system", "Classify each log message as NORMAL, WARNING, CRITICAL, or FATAL. Respond with a comma-separated list of classifications in the same order as the input. Only output the classifications, nothing else."),
                ("human", "{logs}")
            ])

            llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0, api_key=api_key)
            chain = prompt | llm
            response = chain.invoke({"logs": batch_text}, config={"callbacks": [_langfuse_handler()]})
            classifications = [c.strip().upper() for c in response.content.split(",")]

            for i, log in enumerate(state["parsed_logs"]):
                classified_log = {**log}
                if i < len(classifications):
                    classified_log["classification"] = classifications[i]
                else:
                    classified_log["classification"] = "NORMAL"
                classified_logs.append(classified_log)
        except Exception as e:
            # If Groq or LangChain raises for any reason, fallback to deterministic
            print(f"Warning: Groq classification failed ({e}). Falling back to rule-based classifier.")
            api_key = None

    if not api_key:
        # Deterministic rule-based classifier (fast, offline)
        for log in state["parsed_logs"]:
            msg = (log.get("message") or "").lower()
            if any(k in msg for k in ("fatal", "exception", "traceback", "database write failed", "payment failed", "gateway")) or "error" in msg:
                severity = "CRITICAL"
            elif any(k in msg for k in ("warn", "warning", "slow", "latency", "delay")):
                severity = "WARNING"
            else:
                severity = "NORMAL"

            classified_logs.append({**log, "classification": severity})

    get_client().update_current_span(
        metadata={
            "model": "llama-3.1-8b-instant",
            "input_count": len(state["parsed_logs"]),
            "output_count": len(classified_logs),
            "severity_counts": {
                label: sum(1 for item in classified_logs if item.get("classification") == label)
                for label in {item.get("classification", "NORMAL") for item in classified_logs}
            },
        }
    )

    return {**state, "classified_logs": classified_logs}

@observe(name="aggregate_stats", as_type="span", capture_input=False, capture_output=False)
def aggregate_stats_node(state: AgentState) -> AgentState:
    print("--- aggregate_stats ---")
    classified_logs = state.get("classified_logs", [])
    severity_counts: Dict[str, int] = {}
    service_counts: Dict[str, int] = {}
    top_messages: Dict[str, int] = {}

    for log in classified_logs:
        classification = log.get("classification", "NORMAL")
        severity_counts[classification] = severity_counts.get(classification, 0) + 1
        service = log.get("service", "unknown")
        service_counts[service] = service_counts.get(service, 0) + 1
        message = log.get("message", "")
        top_messages[message] = top_messages.get(message, 0) + 1

    repeated_errors = sorted(
        [{"message": message, "count": count} for message, count in top_messages.items()],
        key=lambda item: item["count"],
        reverse=True,
    )[:5]

    stats = {
        "total_count": state.get("total_count", 0),
        "parsed_count": len(classified_logs),
        "severity_counts": severity_counts,
        "affected_services": sorted(service_counts.items(), key=lambda item: item[1], reverse=True),
        "top_repeated_errors": repeated_errors,
    }

    get_client().update_current_span(
        metadata={
            "parsed_count": stats["parsed_count"],
            "severity_counts": severity_counts,
            "affected_services": stats["affected_services"],
        }
    )

    return {**state, "stats": stats}

@observe(name="generate_rca", as_type="span", capture_input=False, capture_output=False)
def generate_rca_node(state: AgentState) -> AgentState:
    print("--- generate_rca ---")
    api_key = os.getenv("GROQ_API_KEY")
    stats = state.get("stats", {})
    top_anomalies = state.get("stats", {}).get("top_repeated_errors", [])
    rca_report = None

    if api_key:
        try:
            from langchain_groq import ChatGroq
            from langchain_core.prompts import ChatPromptTemplate

            llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0, api_key=api_key)

            prompt = ChatPromptTemplate.from_messages([
                (
                    "system",
                    "Produce a structured RCA report in JSON with keys: summary, severity, likely_root_cause, impacted_services, next_actions. Use only the provided stats.",
                ),
                ("human", "Stats: {stats}\nTop anomalies: {anomalies}"),
            ])

            chain = prompt | llm
            response = chain.invoke(
                {"stats": json.dumps(stats), "anomalies": json.dumps(top_anomalies)},
                config={"callbacks": [_langfuse_handler()]},
            )

            try:
                rca_report = json.loads(response.content)
            except json.JSONDecodeError:
                fenced_json = re.search(r"```json\s*(.*?)\s*```", response.content, re.DOTALL)
                if fenced_json:
                    try:
                        rca_report = json.loads(fenced_json.group(1))
                    except json.JSONDecodeError:
                        rca_report = None
                else:
                    rca_report = None

        except Exception as e:
            print(f"Warning: Groq RCA generation failed ({e}). Falling back to rule-based RCA.")
            rca_report = None

    if rca_report is None:
        # Simple deterministic RCA generation using stats
        severity_counts = stats.get("severity_counts", {})
        highest = "NORMAL"
        if severity_counts.get("CRITICAL", 0) > 0:
            highest = "CRITICAL"
        elif severity_counts.get("WARNING", 0) > 0:
            highest = "WARNING"

        likely_root = "Repeated errors in core services"
        if top_anomalies:
            likely_root = top_anomalies[0]["message"] if isinstance(top_anomalies[0], dict) else str(top_anomalies[0])

        impacted = [s for s, _ in stats.get("affected_services", [])][:3]
        next_actions = [
            "Investigate top repeated error messages",
            "Check service resource utilization and error logs",
            "Validate recent deploys or config changes",
        ]

        rca_report = {
            "summary": f"Detected {stats.get('parsed_count',0)} anomalies across services; highest severity: {highest}",
            "severity": highest,
            "likely_root_cause": likely_root,
            "impacted_services": impacted,
            "next_actions": next_actions,
        }

    get_client().update_current_span(
        metadata={
            "model": "llama-3.1-8b-instant",
            "anomaly_count": len(top_anomalies),
            "rca_keys": sorted(rca_report.keys()),
        }
    )

    return {**state, "rca_report": rca_report}

@observe(name="persist_and_emit", as_type="span", capture_input=False, capture_output=False)
def persist_and_emit_node(state: AgentState) -> AgentState:
    print("--- persist_and_emit ---")
    job_id = state.get("job_id") or str(uuid.uuid4())
    os.makedirs("reports", exist_ok=True)

    if state.get("classified_logs"):
        init_db()
        save_logs(state["classified_logs"])

    report_path = os.path.join("reports", f"rca_{job_id}.json")
    with open(report_path, "w", encoding="utf-8") as file:
        json.dump(
            {
                "job_id": job_id,
                "job_status": "completed",
                "stats": state.get("stats", {}),
                "rca_report": state.get("rca_report", {}),
            },
            file,
            indent=2,
        )

    server_url = os.getenv("LOG_ANALYZER_API_URL", "http://127.0.0.1:8000")
    payload = {
        "job_id": job_id,
        "job_status": "completed",
        "stats": state.get("stats", {}),
        "rca_report": state.get("rca_report", {}),
    }

    try:
        response = requests.post(f"{server_url}/logs/report/{job_id}", json=payload, timeout=15)
        response.raise_for_status()
        print(f"Posted RCA report to {server_url}/logs/report/{job_id}")
    except requests.RequestException as error:
        raise RuntimeError(f"Failed to POST RCA report to {server_url}: {error}") from error

    print(f"Saved RCA report to {report_path}")
    print("Job status: completed")

    get_client().update_current_span(
        metadata={
            "job_id": job_id,
            "job_status": "completed",
            "report_path": report_path,
            "server_url": server_url,
        }
    )

    return {**state, "job_id": job_id, "job_status": "completed"}

# Build the graph
def build_graph():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("ingest_logs", read_logs_node)
    workflow.add_node("classify_anomalies", classify_anomalies_node)
    workflow.add_node("aggregate_stats", aggregate_stats_node)
    workflow.add_node("generate_rca", generate_rca_node)
    workflow.add_node("persist_and_emit", persist_and_emit_node)
    
    workflow.set_entry_point("ingest_logs")
    workflow.add_edge("ingest_logs", "classify_anomalies")
    workflow.add_edge("classify_anomalies", "aggregate_stats")
    workflow.add_edge("aggregate_stats", "generate_rca")
    workflow.add_edge("generate_rca", "persist_and_emit")
    workflow.add_edge("persist_and_emit", END)
    
    return workflow.compile()

@observe(name="log_analyzer_run", as_type="span", capture_input=False, capture_output=False)
def run_agent() -> None:
    app = build_graph()
    initial_state = {
        "log_file_path": "app.log",
        "lines": [],
        "parsed_logs": [],
        "classified_logs": [],
        "stats": {},
        "rca_report": {},
        "job_status": "pending",
        "total_count": 0,
        "job_id": str(uuid.uuid4()),
    }

    get_client().update_current_span(
        metadata={
            "job_id": initial_state["job_id"],
            "log_file_path": initial_state["log_file_path"],
        }
    )

    app.invoke(initial_state)


def process_file_sync(log_file_path: str, job_id: str = None, persist: bool = False) -> AgentState:
    """Process a single log file synchronously through the pipeline and return the final state.

    If `persist` is True the `persist_and_emit` node will run and will attempt to write a report
    and POST it to the configured `LOG_ANALYZER_API_URL`.
    """
    if job_id is None:
        job_id = str(uuid.uuid4())

    state: AgentState = {
        "log_file_path": log_file_path,
        "lines": [],
        "parsed_logs": [],
        "classified_logs": [],
        "stats": {},
        "rca_report": {},
        "job_status": "pending",
        "total_count": 0,
        "job_id": job_id,
    }

    # Run nodes sequentially so server can call specific stages synchronously
    state = read_logs_node(state)
    state = classify_anomalies_node(state)
    state = aggregate_stats_node(state)
    state = generate_rca_node(state)
    if persist:
        state = persist_and_emit_node(state)

    return state


def run_job(log_file_path: str, job_id: str = None) -> None:
    """Background-friendly wrapper to run the full pipeline and persist results."""
    process_file_sync(log_file_path=log_file_path, job_id=job_id, persist=True)

if __name__ == "__main__":
    try:
        run_agent()
    except RuntimeError as error:
        print(f"Error: {error}")
        raise SystemExit(1)
