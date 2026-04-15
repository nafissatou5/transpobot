"""
TranspoBot — Backend FastAPI complet
Projet GLSi L3 — ESP/UCAD
Version corrigée Groq + MySQL + Text-to-SQL
"""

import os
import json
import mysql.connector
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# =====================================================
# LOAD ENV
# =====================================================

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")

# =====================================================
# FASTAPI
# =====================================================

app = FastAPI(title="TranspoBot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# DATABASE CONNECTION
# =====================================================

def get_db():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
    )

# =====================================================
# HEALTH CHECK
# =====================================================

@app.get("/health")
def health():
    try:
        db = get_db()
        db.close()

        return {
            "status": "ok",
            "app": "TranspoBot",
            "db": "connected"
        }

    except Exception as e:
        return {
            "status": "error",
            "db": str(e)
        }

# =====================================================
# GROQ CALL
# =====================================================

async def call_llm(prompt: str):

    url = f"{LLM_BASE_URL}/chat/completions"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are a SQL assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            url,
            headers=headers,
            json=payload
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail=response.text
        )

    data = response.json()

    return data["choices"][0]["message"]["content"]

# =====================================================
# CHAT ENDPOINT
# =====================================================

@app.post("/chat")
async def chat(question: dict):

    user_question = question.get("question")

    if not user_question:
        raise HTTPException(status_code=400, detail="Question missing")

    # 1️⃣ Generate SQL from LLM
    sql_query = await call_llm(
        f"Convert this question into MySQL query:\n{user_question}"
    )

    # nettoyage
    sql_query = sql_query.replace("```sql", "").replace("```", "").strip()

    # 2️⃣ Execute SQL
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(sql_query)
        results = cursor.fetchall()

        cursor.close()
        db.close()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "question": user_question,
        "sql": sql_query,
        "results": results
    }
