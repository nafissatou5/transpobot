"""
TranspoBot — Backend FastAPI corrigé avec logs de debug
Projet GLSi L3 — ESP/UCAD
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

app = FastAPI(title="TranspoBot API", version="1.0.1")

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

SYSTEM_PROMPT = f"""Tu es TranspoBot. Réponds uniquement en JSON avec ce format :
{{"sql": "LA_REQUETE_SQL", "explication": "TON_EXPLICATION"}}
Schema: {DB_SCHEMA}
Important: Pas de texte avant ou après le JSON.
"""

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

    async with httpx.AsyncClient() as client:
        print(f"--- Envoi à OpenAI ({LLM_MODEL}) ---")
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
            print(f"Erreur API OpenAI: {response.text}")
            response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]
        print(f"Réponse brute IA : {content}")
        return json.loads(content)

class ChatMessage(BaseModel):
    question: str
    history: list = []

@app.post("/api/chat")
async def chat(msg: ChatMessage):
    try:
        llm_res = await ask_llm(msg.question, msg.history)
        sql = llm_res.get("sql")
        expl = llm_res.get("explication", "Voici le résultat.")

        if not sql:
            return {"answer": expl, "data": [], "sql": None, "count": 0}

        if not is_safe_query(sql):
            raise HTTPException(status_code=400, detail="Requête SQL non autorisée.")

        data = execute_query(sql)
        return {"answer": expl, "data": data, "sql": sql, "count": len(data)}

    except Exception as e:
        print("!!! CRASH DU SERVEUR !!!")
        print(traceback.format_exc()) # Affiche l'erreur exacte dans ton terminal
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    try:
        execute_query("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "error", "db": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
