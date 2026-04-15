import os, json, traceback, httpx
from datetime import datetime
from typing import List, Optional
from理论 import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import mysql.connector

# Charger les variables d'environnement
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="TranspoBot Groq")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Configuration ---
DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "user":     os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "transpobot"),
}

LLM_API_KEY  = os.getenv("OPENAI_API_KEY") 
LLM_MODEL    = os.getenv("LLM_MODEL", "llama3-8b-8192")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")

class ChatMessage(BaseModel):
    question: str
    history: Optional[List] = []

# --- Fonction LLM ---
async def ask_llm(question: str):
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Configuration spécifique et obligatoire pour Groq
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system", 
                "content": "You are a helpful assistant that outputs JSON. Your entire response must be a valid JSON object. The JSON MUST contain two keys: 'sql' and 'explication'."
            },
            {
                "role": "user", 
                "content": f"Generate a JSON response for this request: {question}"
            }
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0
    }
    
    async with httpx.AsyncClient(timeout=20) as client:
        print(f"--> Tentative d'appel Groq...")
        resp = await client.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload)
        
        # SI CA ECHOUE : On affiche le texte brut de l'erreur dans le terminal
        if resp.status_code != 200:
            print("\n" + "!"*30)
            print(f"ERREUR GROQ BRUTE : {resp.text}")
            print("!"*30 + "\n")
            raise Exception(f"Erreur Groq: {resp.status_code}")
            
        content = resp.json()["choices"][0]["message"]["content"]
        print(f"--> Réponse IA reçue : {content}")
        return json.loads(content)

# --- Fonction DB ---
def execute_query(sql: str):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql)
        results = cursor.fetchall()
        for row in results:
            for k, v in row.items():
                if isinstance(v, datetime): row[k] = v.isoformat()
        return results
    finally:
        cursor.close()
        conn.close()

# --- Route principale ---
@app.post("/api/chat")
async def chat(msg: ChatMessage):
    try:
        print(f"--> Question: {msg.question}")
        res = await ask_llm(msg.question)
        
        sql = res.get("sql")
        data = []
        
        if sql and "SELECT" in sql.upper():
            data = execute_query(sql)
            
        return {
            "answer": res.get("explication", ""),
            "data": data,
            "sql": sql
        }
    except Exception as e:
        print(traceback.format_exc())
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.get("/")
def home():
    return FileResponse("index.html")

if __name__ == "__main__":
    import uvicorn
    # On force reload=False pour éviter les bugs de port sur Windows
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
