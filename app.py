import os, re, json, traceback, httpx
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import mysql.connector

load_dotenv()

app = FastAPI(title="TranspoBot Debug Mode")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONFIG ---
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "transpobot"),
}
LLM_API_KEY = os.getenv("OPENAI_API_KEY", "")

# --- MIDDLEWARE DE DEBUG (Pour forcer l'affichage de l'erreur) ---
@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        print("\n" + "="*50)
        print("ERREUR CRITIQUE DÉTECTÉE :")
        print(traceback.format_exc())
        print("="*50 + "\n")
        return JSONResponse(status_code=500, content={"detail": str(e), "traceback": traceback.format_exc()})

# --- FONCTIONS ---
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
    print(f"--> Envoi à OpenAI...")
    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": question}],
                "response_format": {"type": "json_object"},
            },
            timeout=20
        )
        if resp.status_code != 200:
            print(f"Erreur API : {resp.text}")
            raise Exception(f"OpenAI Error: {resp.status_code}")
        return json.loads(resp.json()["choices"][0]["message"]["content"])

class ChatMessage(BaseModel):
    question: str
    history: list = []

# --- ROUTES ---
@app.post("/api/chat")
async def chat(msg: ChatMessage):
    print(f"Question reçue : {msg.question}")
    # Simulation simplifiée pour tester si c'est l'IA qui bloque
    try:
        res = await ask_llm(f"Génère du SQL JSON pour : {msg.question}. Tables: vehicules, trajets.")
        sql = res.get("sql")
        data = execute_query(sql) if sql else []
        return {"answer": res.get("explication"), "data": data, "sql": sql}
    except Exception as e:
        print(f"Erreur dans /api/chat : {e}")
        raise e

@app.get("/api/stats")
def get_stats():
    return {"status": "ok"} # Simplifié pour test rapide

@app.get("/")
def home():
    return FileResponse("index.html")

if __name__ == "__main__":
    import uvicorn
    # On force l'exécution sur localhost et on retire le reloader qui masque les erreurs
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False, access_log=True)
