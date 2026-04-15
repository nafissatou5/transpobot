import os, re, json, traceback, httpx
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request # Ajout de Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse # Ajout de JSONResponse
from pydantic import BaseModel
import mysql.connector

load_dotenv()

app = FastAPI(title="TranspoBot Groq Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Configuration ──────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "user":     os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "transpobot"),
}

LLM_API_KEY  = os.getenv("OPENAI_API_KEY") 
LLM_MODEL    = os.getenv("LLM_MODEL", "llama3-8b-8192")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")

DB_SCHEMA = "Tables: vehicules, chauffeurs, lignes, trajets, incidents."

# ── Fonctions ──────────────────────────────────────────────────────────────
def execute_query(sql: str):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql)
        results = cursor.fetchall()
        cleaned = []
        for row in results:
            clean_row = {}
            for k, v in row.items():
                if isinstance(v, datetime): clean_row[k] = v.isoformat()
                elif hasattr(v, '__float__'): clean_row[k] = float(v)
                else: clean_row[k] = v
            cleaned.append(clean_row)
        return cleaned
    finally:
        cursor.close()
        conn.close()

async def ask_llm(question: str):
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system", 
                "content": "You are a SQL expert. Output your response in JSON format with 'sql' and 'explication' keys."
            },
            {"role": "user", "content": question}
        ],
        "response_format": {"type": "json_object"}
    }
    
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload)
        if resp.status_code != 200:
            print(f"ERREUR GROQ: {resp.text}")
            raise Exception(f"Erreur API Groq: {resp.status_code}")
        return json.loads(resp.json()["choices"][0]["message"]["content"])

class ChatMessage(BaseModel):
    question: str
    history: list = []

# ── Routes ─────────────────────────────────────────────────────────────────
@app.post("/api/chat")
async def chat(msg: ChatMessage): # Retour au modèle propre
    try:
        print(f"DEBUG: Question reçue -> {msg.question}")
        
        # Appel réel à l'IA
        res = await ask_llm(msg.question)
        sql = res.get("sql")
        
        data = []
        if sql and sql.strip().upper().startswith("SELECT"):
            data = execute_query(sql)
            
        return {
            "answer": res.get("explication", "Voici le résultat"),
            "data": data, 
            "sql": sql,
            "count": len(data)
        }
    except Exception as e:
        print("!!! ERREUR SERVEUR !!!")
        print(traceback.format_exc())
        return JSONResponse(
            status_code=500, 
            content={"detail": str(e), "traceback": "Voir terminal"}
        )

@app.get("/api/stats")
def get_stats():
    return {"status": "ok"}

@app.get("/")
def home():
    return FileResponse("index.html")

if __name__ == "__main__":
    import uvicorn
    # Désactive le reload pour stabiliser MINGW64
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
