import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("DB_NAME", "logs.db")

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            level TEXT,
            service TEXT,
            message TEXT,
            classification TEXT
        )
    ''')
    # Simple migration to add classification column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE logs ADD COLUMN classification TEXT")
    except sqlite3.OperationalError:
        # Column already exists
        pass
    conn.commit()
    conn.close()

def save_logs(logs):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.executemany('''
        INSERT INTO logs (timestamp, level, service, message, classification)
        VALUES (?, ?, ?, ?, ?)
    ''', [(l['timestamp'], l['level'], l['service'], l['message'], l.get('classification', 'NORMAL')) for l in logs])
    conn.commit()
    conn.close()

def get_summary():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT classification, COUNT(*) as count 
        FROM logs 
        GROUP BY classification
    ''')
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}
