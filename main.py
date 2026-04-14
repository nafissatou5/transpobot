"""
TranspoBot — Backend FastAPI complet
Projet GLSi L3 — ESP/UCAD
"""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import mysql.connector
import os, re, json
import httpx
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="TranspoBot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── CONFIG ─────────────────────────────────────────────
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "transpobot"),
    "charset": "utf8mb4",
}

LLM_API_KEY  = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL    = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")

PORT = int(os.getenv("PORT", 8000))  # ✅ IMPORTANT RAILWAY

# ── SCHÉMA ─────────────────────────────────────────────
DB_SCHEMA = """
Tables MySQL disponibles dans la base 'transpobot' :

vehicules(id, immatriculation, type ENUM['bus','minibus','taxi'], capacite INT,
          statut ENUM['actif','maintenance','hors_service'], kilometrage INT, date_acquisition DATE)

chauffeurs(id, nom, prenom, telephone, numero_permis, categorie_permis,
           disponibilite BOOLEAN, vehicule_id FK→vehicules, date_embauche DATE)

lignes(id, code, nom, origine, destination, distance_km DECIMAL, duree_minutes INT)

tarifs(id, ligne_id FK→lignes, type_client ENUM['normal','etudiant','senior'], prix DECIMAL)

trajets(id, ligne_id FK→lignes, chauffeur_id FK→chauffeurs, vehicule_id FK→vehicules,
        date_heure_depart DATETIME, date_heure_arrivee DATETIME,
        statut ENUM['planifie','en_cours','termine','annule'],
        nb_passagers INT, recette DECIMAL)

incidents(id, trajet_id FK→trajets, type ENUM['panne','accident','retard','autre'],
          description TEXT, gravite ENUM['faible','moyen','grave'],
          date_incident DATETIME, resolu BOOLEAN)
"""

SYSTEM_PROMPT = f"""
Tu es TranspoBot, assistant SQL.

{DB_SCHEMA}

Règles :
- SELECT uniquement
- JSON obligatoire:
{{"sql": "...", "explication": "..."}}
- sinon:
{{"sql": null, "explication": "..."}}
"""

# ── DB ─────────────────────────────────────────────
def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def execute_query(sql: str):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql)
        results = cursor.fetchall()

        cleaned = []
        for row in results:
            clean = {}
            for k, v in row.items():
                if isinstance(v, datetime):
                    clean[k] = v.isoformat()
                elif hasattr(v, "__float__"):
                    clean[k] = float(v)
                else:
                    clean[k] = v
            cleaned.append(clean)

        return cleaned
    finally:
        cursor.close()
        conn.close()

# ── sécurité SQL ─────────────────────────────────────
FORBIDDEN = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b',
    re.IGNORECASE
)

def is_safe_query(sql: str) -> bool:
    if not sql:
        return False
    if FORBIDDEN.search(sql):
        return False
    return sql.strip().upper().startswith("SELECT")

# ── LLM ─────────────────────────────────────────────
async def ask_llm(question: str):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

# ── MODELE ───────────────────────────────────────────
class ChatMessage(BaseModel):
    question: str
    history: list = []

# ── ROUTE CHAT ───────────────────────────────────────
@app.post("/api/chat")
async def chat(msg: ChatMessage):
    try:
        raw = await ask_llm(msg.question)
        llm = json.loads(raw)

        sql = llm.get("sql")
        exp = llm.get("explication", "")

        if not sql:
            return {"answer": exp, "data": [], "sql": None, "count": 0}

        if not is_safe_query(sql):
            raise HTTPException(400, "SQL interdit")

        data = execute_query(sql)

        return {
            "answer": exp,
            "sql": sql,
            "data": data,
            "count": len(data),
        }

    except Exception as e:
        raise HTTPException(500, str(e))

# ── HEALTH CHECK ─────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}

# ── ROOT ─────────────────────────────────────────────
@app.get("/")
def root():
    return {"message": "TranspoBot API running"}

# ── RAILWAY START ────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
