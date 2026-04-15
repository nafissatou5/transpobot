"""
TranspoBot — Backend FastAPI complet
Projet GLSi L3 — ESP/UCAD
Version corrigée Groq + MySQL + Text-to-SQL
"""

import os
import json
import traceback
import httpx
from datetime import datetime
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import mysql.connector

# ===============================
# Charger variables environnement
# ===============================
load_dotenv()

print("GROQ KEY =", os.getenv("GROQ_API_KEY"))

# ===============================
# App FastAPI
# ===============================
app = FastAPI(title="TranspoBot Groq")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===============================
# Configuration DB
# ===============================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "transpobot"),
}

# ===============================
# Configuration LLM (Groq)
# ===============================
LLM_API_KEY = os.getenv("GROQ_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3-8b-8192")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")

# ===============================
# Modèle requête
# ===============================
class ChatMessage(BaseModel):
    question: str
    history: Optional[List] = []


# ===============================
# Appel LLM Groq
# ===============================
async def ask_llm(question: str):

    if not LLM_API_KEY:
        raise Exception("GROQ_API_KEY manquante dans .env")

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Text-to-SQL assistant.\n"
                    "Return ONLY a valid JSON object.\n"
                    "Format:\n"
                    "{\n"
                    "  \"sql\": \"SQL QUERY\",\n"
                    "  \"explication\": \"French explanation\"\n"
                    "}"
                )
            },
            {
                "role": "user",
                "content": question
            }
        ],
        "temperature": 0
    }

    async with httpx.AsyncClient(timeout=30) as client:

        print("➡️ Appel Groq...")
        resp = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers=headers,
            json=payload
        )

        print("STATUS:", resp.status_code)
        print("RAW RESPONSE:", resp.text)

        resp.raise_for_status()

        content = resp.json()["choices"][0]["message"]["content"]

        return json.loads(content)


# ===============================
# Exécution SQL
# ===============================
def execute_query(sql: str):

    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(sql)
        results = cursor.fetchall()

        # convertir datetime → JSON
        for row in results:
            for k, v in row.items():
                if isinstance(v, datetime):
                    row[k] = v.isoformat()

        return results

    finally:
        cursor.close()
        conn.close()


# ===============================
# Route Chat principale
# ===============================
@app.post("/api/chat")
async def chat(msg: ChatMessage):

    try:
        print(f"QUESTION : {msg.question}")

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


# ===============================
# Page accueil
# ===============================
@app.get("/")
def home():
    return FileResponse("index.html")


# ===============================
# Lancement serveur
# ===============================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
