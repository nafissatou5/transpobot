"""
TranspoBot — Backend FastAPI complet
Projet GLSi L3 — ESP/UCAD
Version stable Groq + MySQL + Text-to-SQL 
"""

import os
import json
import traceback
import httpx
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import mysql.connector


# =====================================================
# Chargement .env (ROBUSTE)
# =====================================================
env_path = Path(__file__).resolve().parent / ".env"

if not env_path.exists():
    raise RuntimeError("❌ Fichier .env introuvable")

load_dotenv(env_path, override=True)


# =====================================================
# CONFIG LLM (UNE SEULE SOURCE)
# =====================================================
LLM_API_KEY = (os.getenv("GROQ_API_KEY") or "").strip()

if not LLM_API_KEY:
    raise RuntimeError("❌ GROQ_API_KEY manquante ou vide dans .env")

LLM_MODEL = os.getenv("LLM_MODEL", "llama3-8b-8192")

LLM_BASE_URL = os.getenv(
    "LLM_BASE_URL",
    "https://api.groq.com/openai/v1"
)

print("--- DEBUG CONFIG ---")
print("ENV GROQ OK :", bool(LLM_API_KEY))
print("KEY PREVIEW :", LLM_API_KEY[:8] + "...")
print("--------------------")


# =====================================================
# APP FASTAPI
# =====================================================
app = FastAPI(title="TranspoBot Groq")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================================================
# CONFIG DATABASE
# =====================================================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "transpobot"),
}


# =====================================================
# MODELE REQUETE
# =====================================================
class ChatMessage(BaseModel):
    question: str
    history: Optional[List] = []


# =====================================================
# APPEL LLM GROQ
# =====================================================
async def ask_llm(question: str):

    headers = {
        "Authorization": "Bearer " + LLM_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Text-to-SQL assistant.\n"
                    "Return ONLY valid JSON.\n"
                    "Format:\n"
                    "{\"sql\":\"SQL QUERY\",\"explication\":\"French explanation\"}"
                )
            },
            {
                "role": "user",
                "content": question
            }
        ],
        "temperature": 0
    }

    print("➡️ Appel Groq...")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers=headers,
            json=payload
        )

        print("STATUS:", resp.status_code)
        print("RAW:", resp.text)

        resp.raise_for_status()

        content = resp.json()["choices"][0]["message"]["content"]

        try:
            return json.loads(content)
        except Exception:
            start = content.find("{")
            end = content.rfind("}") + 1
            return json.loads(content[start:end])


# =====================================================
# EXECUTION SQL
# =====================================================
def execute_query(sql: str):

    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(sql)
        results = cursor.fetchall()

        for row in results:
            for k, v in row.items():
                if isinstance(v, datetime):
                    row[k] = v.isoformat()

        return results

    finally:
        cursor.close()
        conn.close()


# =====================================================
# ROUTE CHAT
# =====================================================
@app.post("/api/chat")
async def chat(msg: ChatMessage):

    try:
        print("QUESTION:", msg.question)

        llm_response = await ask_llm(msg.question)

        sql = llm_response.get("sql")
        data = []

        if sql and "SELECT" in sql.upper():
            data = execute_query(sql)

        return {
            "answer": llm_response.get("explication", ""),
            "sql": sql,
            "data": data
        }

    except Exception as e:
        print(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"detail": str(e)}
        )


# =====================================================
# HOME PAGE
# =====================================================
@app.get("/")
def home():
    return FileResponse("index.html")


# =====================================================
# RUN SERVER
# =====================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
