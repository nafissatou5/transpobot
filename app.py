import os, re, json, traceback, httpx
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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

# ── Configuration (Récupérée du .env) ──────────────────────────────────────
DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "user":     os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "transpobot"),
}

LLM_API_KEY  = os.getenv("OPENAI_API_KEY") # Ta clé Groq gsk_...
LLM_MODEL    = os.getenv("LLM_MODEL", "llama3-8b-8192")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")

DB_SCHEMA = "Tables: vehicules, chauffeurs, lignes, tarifs, trajets, incidents."

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
    # Important : On utilise l'URL et la clé du .env
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"}
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": f"Tu es un expert SQL. Réponds en JSON strict : {{\"sql\": \"...\", \"explication\": \"...\"}}. Schema: {DB_SCHEMA}"},
            {"role": "user", "content": question}
        ],
        "response_format": {"type": "json_object"}
    }
    
    async with httpx.AsyncClient(timeout=20) as client:
        print(f"--> Envoi à Groq ({LLM_MODEL})...")
        resp = await client.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload)
        
        if resp.status_code != 200:
            print(f"Erreur API : {resp.text}")
            raise Exception(f"API Error {resp.status_code}")
            
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)

class ChatMessage(BaseModel):
    question: str
    history: list = []

# ── Routes ─────────────────────────────────────────────────────────────────
@app.post("/api/chat")
async def chat(request: Request): # On utilise Request au lieu de ChatMessage
    try:
        # On lit le corps de la requête manuellement
        body = await request.json()
        question = body.get("question")
        print(f"DEBUG: Question reçue -> {question}")
        
        # Test ultra simple sans IA pour voir si ça répond
        return {"answer": f"J'ai bien reçu : {question}", "data": [], "sql": None}
    except Exception as e:
        print(f"ERREUR LECTURE JSON: {e}")
        return JSONResponse(status_code=400, content={"error": "JSON invalide"})

@app.get("/api/stats")
def get_stats():
    return {"status": "ok"}

@app.get("/")
def home():
    return FileResponse("index.html")

if __name__ == "__main__":
    import uvicorn
    # Désactive le reload pour plus de stabilité pendant le débug
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
