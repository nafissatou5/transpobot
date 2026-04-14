"""
TranspoBot — Backend FastAPI complet
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import mysql.connector
import os, re, json
import httpx
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ===================== APP =====================
app = FastAPI(title="TranspoBot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===================== CONFIG =====================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "transpobot"),
}

LLM_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_BASE_URL = "https://api.openai.com/v1"

PORT = int(os.getenv("PORT", 8000))

# ===================== ROOT (IMPORTANT) =====================
@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "TranspoBot API running",
        "docs": "/docs",
        "health": "/health"
    }

# ===================== HEALTH =====================
@app.get("/health")
def health():
    return {"status": "ok"}

# ===================== DB =====================
def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def execute_query(sql: str):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql)
        results = cursor.fetchall()

        cleaned = []
        for row in results:
            clean = {}
            for k, v in row.items():
                if isinstance(v, datetime):
                    clean[k] = v.isoformat()
                elif hasattr(v, "__float__"):
                    clean[k] = float(v)
                else:
                    clean[k] = v
            cleaned.append(clean)

        return cleaned
    finally:
        cursor.close()
        conn.close()

# ===================== SECURITY =====================
FORBIDDEN = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b',
    re.IGNORECASE
)

def is_safe_query(sql: str):
    return sql and not FORBIDDEN.search(sql) and sql.strip().upper().startswith("SELECT")

# ===================== LLM =====================
async def ask_llm(question: str):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": "Tu génères du SQL SELECT uniquement en JSON."},
                    {"role": "user", "content": question},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])

# ===================== MODEL =====================
class ChatMessage(BaseModel):
    question: str
    history: list = []

# ===================== CHAT =====================
@app.post("/api/chat")
async def chat(msg: ChatMessage):
    try:
        llm = await ask_llm(msg.question)

        sql = llm.get("sql")
        exp = llm.get("explication", "")

        if not sql:
            return {"answer": exp, "data": [], "sql": None, "count": 0}

        if not is_safe_query(sql):
            raise HTTPException(400, "SQL interdit")

        data = execute_query(sql)

        return {
            "answer": exp,
            "sql": sql,
            "data": data,
            "count": len(data),
        }

    except Exception as e:
        raise HTTPException(500, str(e))
