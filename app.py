"""
TranspoBot — Backend FastAPI FINAL STABLE
Groq + MySQL + Text-to-SQL
ESP / UCAD GLSI L3
"""

import os
import re
import json
import traceback
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

import httpx
import mysql.connector
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# =====================================================
# LOAD .ENV (FIX WINDOWS ^M BUG)
# =====================================================

env_path = Path(__file__).parent / ".env"

if env_path.exists():
    with open(env_path, encoding="utf-8") as f:
        for line in f.read().splitlines():
            line = line.replace("\r", "").strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

# =====================================================
# CONFIG
# =====================================================

LLM_API_KEY = os.getenv("GROQ_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3-8b-8192")

# ✅ IMPORTANT — BASE URL CORRECTE
LLM_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "transpobot"),
    "charset": "utf8mb4",
}

print("LLM OK:", bool(LLM_API_KEY))

# =====================================================
# FASTAPI
# =====================================================

app = FastAPI(title="TranspoBot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# MODELS
# =====================================================

class ChatMessage(BaseModel):
    question: str
    history: Optional[List] = []

# =====================================================
# MYSQL
# =====================================================

def clean(v):
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v

def execute_query(sql: str):

    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)

    try:
        cur.execute(sql)
        rows = cur.fetchall()
        return [{k: clean(v) for k, v in r.items()} for r in rows]
    finally:
        cur.close()
        conn.close()

# =====================================================
# PROMPT
# =====================================================

def build_prompt():

    today = datetime.now().strftime("%Y-%m-%d")

    return f"""
Tu es TranspoBot.

DATE: {today}

Réponds uniquement en JSON:

{{"sql":"SELECT ...","explication":"texte"}}

SELECT uniquement.
LIMIT 100 obligatoire.
"""

# =====================================================
# GROQ CALL
# =====================================================

async def call_llm(question: str, history=None):

    if not LLM_API_KEY:
        raise ValueError("GROQ_API_KEY manquant")

    messages = [
        {"role": "system", "content": build_prompt()},
        {"role": "user", "content": question},
    ]

    async with httpx.AsyncClient(timeout=40) as client:

        r = await client.post(
            LLM_BASE_URL,
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": messages,
                "temperature": 0,
            },
        )

    print("GROQ STATUS:", r.status_code)

    if r.status_code != 200:
        print(r.text)
        r.raise_for_status()

    content = r.json()["choices"][0]["message"]["content"]

    content = re.sub(r"```json|```", "", content).strip()

    try:
        return json.loads(content)
    except:
        return {"sql": None, "explication": content}

# =====================================================
# SECURITY SQL
# =====================================================

FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b",
    re.I,
)

# =====================================================
# CHAT API
# =====================================================

@app.post("/api/chat")
async def chat(msg: ChatMessage):

    try:

        result = await call_llm(msg.question)

        sql = result.get("sql")
        explanation = result.get("explication", "")

        if not sql:
            return {"answer": explanation, "data": []}

        if FORBIDDEN.search(sql):
            return JSONResponse(
                status_code=400,
                content={"detail": "Requête interdite"},
            )

        data = execute_query(sql)

        return {
            "answer": explanation,
            "sql": sql,
            "data": data,
            "count": len(data),
        }

    except Exception as e:

        print(traceback.format_exc())

        return JSONResponse(
            status_code=500,
            content={"detail": str(e)},
        )

# =====================================================
# HEALTH CHECK
# =====================================================

@app.get("/health")
def health():

    try:
        execute_query("SELECT 1")
        return {
            "status": "ok",
            "db": "connected",
            "llm": bool(LLM_API_KEY),
        }
    except Exception as e:
        return {"status": "error", "db": str(e)}

# =====================================================
# ROOT
# =====================================================

@app.get("/")
def root():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"message": "TranspoBot running"}

# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", reload=True)
