import re
import os
from typing import TypedDict, List, Dict
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

# Load environment variables
load_dotenv()
from db_manager import init_db, save_logs

# Define the state
class AgentState(TypedDict):
    log_file_path: str
    lines: List[str]
    parsed_logs: List[Dict]
    classification_results: List[str]
    success_count: int
    total_count: int
    ratio: float

# Regex for parsing: "2026-05-13 12:00:01 INFO [AuthService] User logged in"
LOG_PATTERN = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) \[(\w+)\] (.*)$')

def read_logs_node(state: AgentState) -> AgentState:
    print("--- Reading Logs ---")
    path = state["log_file_path"]
    if not os.path.exists(path):
        print(f"Error: {path} not found.")
        return {**state, "lines": []}
    
    with open(path, "r") as f:
        lines = [line.strip() for line in f if line.strip()]
    
    return {**state, "lines": lines, "total_count": len(lines)}

def parse_logs_node(state: AgentState) -> AgentState:
    print("--- Parsing Logs ---")
    parsed_logs = []
    success_count = 0
    
    for line in state["lines"]:
        match = LOG_PATTERN.match(line)
        if match:
            timestamp, level, service, message = match.groups()
            parsed_logs.append({
                "timestamp": timestamp,
                "level": level,
                "service": service,
                "message": message
            })
            success_count += 1
        else:
            print(f"Skipping malformed line: {line}")
            
    return {**state, "parsed_logs": parsed_logs, "success_count": success_count}

def classify_logs_node(state: AgentState) -> AgentState:
    print("--- Classifying Logs with Groq ---")
    from langchain_groq import ChatGroq
    from langchain_core.prompts import ChatPromptTemplate
    
    if not state["parsed_logs"]:
        return state
        
    llm = ChatGroq(
        model="llama3-8b-8192",
        temperature=0,
        api_key=os.getenv("GROQ_API_KEY")
    )
    
    # Batch processing
    batch_text = "\n".join([f"{i}: {log['message']}" for i, log in enumerate(state["parsed_logs"])])
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Classify each log message as NORMAL, WARNING, or CRITICAL. Respond with a comma-separated list of classifications in the same order as the input. Only output the classifications, nothing else."),
        ("human", "{logs}")
    ])
    
    chain = prompt | llm
    response = chain.invoke({"logs": batch_text})
    
    classifications = [c.strip().upper() for c in response.content.split(",")]
    
    # Attach classifications to parsed_logs
    for i, log in enumerate(state["parsed_logs"]):
        if i < len(classifications):
            log["classification"] = classifications[i]
        else:
            log["classification"] = "NORMAL" # Fallback
            
    return {**state, "classification_results": classifications}

def save_to_db_node(state: AgentState) -> AgentState:
    print("--- Saving to Database ---")
    if state["parsed_logs"]:
        init_db()
        save_logs(state["parsed_logs"])
    return state

def report_stats_node(state: AgentState) -> AgentState:
    print("--- Final Report ---")
    total = state["total_count"]
    success = state["success_count"]
    ratio = (success / total * 100) if total > 0 else 0
    
    print(f"Total lines processed: {total}")
    print(f"Successfully parsed: {success}")
    print(f"Malformed lines: {total - success}")
    print(f"Success Ratio: {ratio:.2f}%")
    
    return {**state, "ratio": ratio}

# Build the graph
def build_graph():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("read_logs", read_logs_node)
    workflow.add_node("parse_logs", parse_logs_node)
    workflow.add_node("classify_logs", classify_logs_node)
    workflow.add_node("save_to_db", save_to_db_node)
    workflow.add_node("report_stats", report_stats_node)
    
    workflow.set_entry_point("read_logs")
    workflow.add_edge("read_logs", "parse_logs")
    workflow.add_edge("parse_logs", "classify_logs")
    workflow.add_edge("classify_logs", "save_to_db")
    workflow.add_edge("save_to_db", "report_stats")
    workflow.add_edge("report_stats", END)
    
    return workflow.compile()

if __name__ == "__main__":
    app = build_graph()
    initial_state = {
        "log_file_path": "app.log",
        "lines": [],
        "parsed_logs": [],
        "classification_results": [],
        "success_count": 0,
        "total_count": 0,
        "ratio": 0.0
    }
    app.invoke(initial_state)
