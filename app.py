"""
TranspoBot — Backend FastAPI
Correction : Debug Forcé & Stabilité Windows
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import mysql.connector
import os, re, json, traceback
import httpx
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="TranspoBot API", version="1.0.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Configuration ──────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "user":     os.getenv("DB_USER",     "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME",     "transpobot"),
    "charset":  "utf8mb4",
}

LLM_API_KEY  = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL    = os.getenv("LLM_MODEL",    "gpt-4o-mini")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")

DB_SCHEMA = """
Tables :
vehicules(id, immatriculation, type, capacite, statut, kilometrage, date_acquisition)
chauffeurs(id, nom, prenom, telephone, numero_permis, disponibilite, vehicule_id)
lignes(id, code, nom, origine, destination, distance_km)
trajets(id, ligne_id, chauffeur_id, vehicule_id, date_heure_depart, statut, nb_passagers, recette)
incidents(id, trajet_id, type, description, gravite, date_incident, resolu)
"""

SYSTEM_PROMPT = f"""Tu es TranspoBot. Réponds UNIQUEMENT en JSON :
{{"sql": "SELECT...", "explication": "..."}}
Schema: {DB_SCHEMA}
"""

def log_error(msg):
    """Écrit l'erreur dans un fichier pour être sûr de la lire."""
    with open("debug_log.txt", "a", encoding="utf-8") as f:
        f.write(f"\n[{datetime.now()}] {msg}\n")

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

def is_safe_query(sql: str) -> bool:
    if not sql: return False
    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE"]
    return not any(word in sql.upper() for word in forbidden) and sql.strip().upper().startswith("SELECT")

async def ask_llm(question: str, history: list = None) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history: messages.extend(history[-6:])
    messages.append({"role": "user", "content": question})

    async with httpx.AsyncClient(verify=False) as client: # verify=False évite les soucis SSL Windows
        print(f"--> Appel LLM pour : {question}")
        response = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "messages": messages,
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        
        if response.status_code != 200:
            err = f"Erreur OpenAI {response.status_code}: {response.text}"
            log_error(err)
            raise Exception(err)

        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)

class ChatMessage(BaseModel):
    question: str
    history: list = []

@app.post("/api/chat")
async def chat(msg: ChatMessage):
    try:
        llm_res = await ask_llm(msg.question, msg.history)
        sql = llm_res.get("sql")
        expl = llm_res.get("explication", "Résultat trouvé.")

        if not sql:
            return {"answer": expl, "data": [], "sql": None, "count": 0}

        if not is_safe_query(sql):
            raise HTTPException(status_code=400, detail="SQL non autorisé.")

        data = execute_query(sql)
        return {"answer": expl, "data": data, "sql": sql, "count": len(data)}

    except Exception as e:
        err_stack = traceback.format_exc()
        print("!!! ERREUR DETECTEE !!! Regardez debug_log.txt")
        log_error(err_stack)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    try:
        execute_query("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "error", "db": str(e)}

@app.get("/")
def serve_index():
    return FileResponse("index.html")

if __name__ == "__main__":
    import uvicorn
    # On force log_level à debug et on désactive le reload
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="debug", reload=False)
