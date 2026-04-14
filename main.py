"""
TranspoBot — Backend FastAPI complet (Railway-ready)
Projet GLSi L3 — ESP/UCAD
"""

import os
import re
import json
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

import httpx
from dotenv import load_dotenv

# ── SAFE IMPORT MYSQL (évite crash Railway) ────────────────────────────────
try:
    import mysql.connector
except Exception as e:
    print("❌ MySQL import error:", e)
    mysql = None

print("🚀 TranspoBot starting...")

load_dotenv()

app = FastAPI(title="TranspoBot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Configuration ──────────────────────────────────────────────────────────
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "transpobot"),
    "charset": "utf8mb4",
}

LLM_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")

# ── Schéma BDD ─────────────────────────────────────────────────────────────
DB_SCHEMA = """
Tables MySQL disponibles dans la base 'transpobot' :

vehicules(id, immatriculation, type, capacite, statut, kilometrage, date_acquisition)
chauffeurs(id, nom, prenom, telephone, numero_permis, categorie_permis, disponibilite, vehicule_id)
lignes(id, code, nom, origine, destination, distance_km, duree_minutes)
tarifs(id, ligne_id, type_client, prix)
trajets(id, ligne_id, chauffeur_id, vehicule_id, date_heure_depart, date_heure_arrivee, statut, nb_passagers, recette)
incidents(id, trajet_id, type, description, gravite, date_incident, resolu)
"""

SYSTEM_PROMPT = f"""
Tu es TranspoBot.

{DB_SCHEMA}

Règles:
- uniquement SELECT
- JSON: {{"sql": "...", "explication": "..."}}
- si impossible: {{"sql": null, "explication": "..."}}
"""

# ── DB CONNECTION ──────────────────────────────────────────────────────────
def get_db():
    if mysql is None:
        raise Exception("MySQL not available")
    return mysql.connector.connect(**DB_CONFIG)

def execute_query(sql: str):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql)
        results = cursor.fetchall()

        cleaned = []
        for row in results:
            clean_row = {}
            for k, v in row.items():
                if isinstance(v, datetime):
                    clean_row[k] = v.isoformat()
                elif hasattr(v, "__float__"):
                    clean_row[k] = float(v)
                else:
                    clean_row[k] = v
            cleaned.append(clean_row)

        return cleaned
    finally:
        cursor.close()
        conn.close()

# ── sécurité SQL ───────────────────────────────────────────────────────────
FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b",
    re.IGNORECASE
)

def is_safe_query(sql: str) -> bool:
    if not sql:
        return False
    if FORBIDDEN.search(sql):
        return False
    return sql.strip().upper().startswith(("SELECT", "WITH"))

# ── LLM ────────────────────────────────────────────────────────────────────
async def ask_llm(question: str, history: list = None):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.append({"role": "user", "content": question})

    async with httpx.AsyncClient() as client:
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

        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]

        try:
            return json.loads(content)
        except Exception:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise Exception("Invalid LLM JSON")

# ── MODELE ─────────────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    question: str
    history: list = []

# ── ROUTES ────────────────────────────────────────────────────────────────
@app.get("/")
def home():
    return {"status": "TranspoBot running"}

@app.post("/api/chat")
async def chat(msg: ChatMessage):
    try:
        llm_response = await ask_llm(msg.question, msg.history)

        sql = llm_response.get("sql")
        explication = llm_response.get("explication", "")

        if not sql:
            return {"answer": explication, "data": [], "sql": None, "count": 0}

        if not is_safe_query(sql):
            raise HTTPException(400, "Requête SQL non autorisée")

        data = execute_query(sql)

        return {
            "answer": explication,
            "data": data,
            "sql": sql,
            "count": len(data),
        }

    except Exception as e:
        raise HTTPException(500, str(e))

# ── HEALTH CHECK ───────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}
