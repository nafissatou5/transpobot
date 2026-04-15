"""
TranspoBot — Backend FastAPI complet
Projet GLSi L3 — ESP/UCAD
Version stable Groq + MySQL + Text-to-SQL
"""

import os
import re
import json
import traceback
import httpx
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import mysql.connector

# ── Chargement .env ROBUSTE (corrige le bug dernière ligne sans retour chariot) ──
env_path = Path(__file__).resolve().parent / ".env"
if not env_path.exists():
    raise RuntimeError("❌ Fichier .env introuvable")

# Lire manuellement pour ne pas rater la dernière ligne sans \n
with open(env_path, "r", encoding="utf-8") as f:
    for line in f.read().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

load_dotenv(env_path, override=True)

# ── Config LLM ─────────────────────────────────────────────────────────────
LLM_API_KEY  = os.environ.get("GROQ_API_KEY", "").strip()
LLM_MODEL    = os.environ.get("LLM_MODEL",    "llama3-8b-8192").strip()
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1").strip()

if not LLM_API_KEY:
    raise RuntimeError("❌ GROQ_API_KEY manquante — vérifie le .env")

print(f"=== TranspoBot démarré ===")
print(f"MODEL   : {LLM_MODEL}")
print(f"API KEY : {LLM_API_KEY[:10]}...")
print(f"=========================")

# ── Config DB ──────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     os.environ.get("DB_HOST",     "localhost"),
    "user":     os.environ.get("DB_USER",     "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME",     "transpobot"),
    "charset":  "utf8mb4",
}

# ── Prompt système COMPLET avec schéma BDD ────────────────────────────────
SYSTEM_PROMPT = """Tu es TranspoBot, assistant Text-to-SQL pour une compagnie de transport sénégalaise.

BASE DE DONNÉES MySQL (base: transpobot) :

vehicules(id, immatriculation, type ENUM['bus','minibus','taxi'], capacite INT,
          statut ENUM['actif','maintenance','hors_service'], kilometrage INT, date_acquisition DATE)

chauffeurs(id, nom, prenom, telephone, numero_permis, categorie_permis,
           disponibilite BOOLEAN, vehicule_id FK→vehicules, date_embauche DATE)

lignes(id, code, nom, origine, destination, distance_km, duree_minutes)

tarifs(id, ligne_id FK→lignes, type_client ENUM['normal','etudiant','senior'], prix DECIMAL)

trajets(id, ligne_id FK→lignes, chauffeur_id FK→chauffeurs, vehicule_id FK→vehicules,
        date_heure_depart DATETIME, date_heure_arrivee DATETIME,
        statut ENUM['planifie','en_cours','termine','annule'],
        nb_passagers INT, recette DECIMAL)

incidents(id, trajet_id FK→trajets, type ENUM['panne','accident','retard','autre'],
          description TEXT, gravite ENUM['faible','moyen','grave'],
          date_incident DATETIME, resolu BOOLEAN)

RÈGLES ABSOLUES :
1. Génère UNIQUEMENT des requêtes SELECT.
2. Réponds UNIQUEMENT en JSON valide, SANS markdown, SANS backticks.
3. Format EXACT : {"sql":"SELECT ...","explication":"Explication en français"}
4. Si hors BDD : {"sql":null,"explication":"Réponse en français"}
5. LIMIT 100 maximum.
6. Valeurs ENUM sans accents : 'termine' (pas 'terminé'), 'planifie', 'en_cours', 'annule'.
7. Pour "cette semaine" : date_heure_depart >= DATE_SUB(NOW(), INTERVAL 7 DAY)
8. Pour "ce mois" : MONTH(col)=MONTH(NOW()) AND YEAR(col)=YEAR(NOW())

EXEMPLES :
Q: "Combien de trajets cette semaine ?"
R: {"sql":"SELECT COUNT(*) AS nb FROM trajets WHERE date_heure_depart >= DATE_SUB(NOW(), INTERVAL 7 DAY) AND statut='termine'","explication":"Nombre de trajets terminés cette semaine."}

Q: "Quel chauffeur a le plus d incidents ?"
R: {"sql":"SELECT c.nom, c.prenom, COUNT(i.id) AS nb FROM incidents i JOIN trajets t ON i.trajet_id=t.id JOIN chauffeurs c ON t.chauffeur_id=c.id GROUP BY c.id ORDER BY nb DESC LIMIT 1","explication":"Le chauffeur avec le plus d incidents."}

Q: "Vehicules en maintenance ?"
R: {"sql":"SELECT immatriculation, type, kilometrage FROM vehicules WHERE statut='maintenance'","explication":"Véhicules en maintenance."}
"""

# ── App FastAPI ────────────────────────────────────────────────────────────
app = FastAPI(title="TranspoBot API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ChatMessage(BaseModel):
    question: str
    history: Optional[List] = []

FORBIDDEN = re.compile(r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE)\b', re.IGNORECASE)

def clean_row(row):
    out = {}
    for k, v in row.items():
        if isinstance(v, datetime): out[k] = v.isoformat()
        elif isinstance(v, Decimal): out[k] = float(v)
        elif isinstance(v, bytes): out[k] = v.decode("utf-8", errors="replace")
        else: out[k] = v
    return out

def execute_query(sql: str):
    conn = mysql.connector.connect(**DB_CONFIG)
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(sql)
        return [clean_row(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()

async def ask_llm(question: str, history: list = None) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        for h in history[-6:]:
            if isinstance(h, dict) and "role" in h and "content" in h:
                messages.append(h)
    messages.append({"role": "user", "content": question})

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"},
            json={"model": LLM_MODEL, "messages": messages, "temperature": 0},
        )
        print(f"Groq status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"Groq error: {resp.text}")
            resp.raise_for_status()

        content = resp.json()["choices"][0]["message"]["content"].strip()
        print(f"LLM raw: {content[:300]}")

        # Nettoyer les backticks markdown
        content = re.sub(r"```(?:json)?", "", content).strip().strip("`").strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r'\{.*\}', content, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except:
                    pass
            return {"sql": None, "explication": content}

# ══ ROUTES ════════════════════════════════════════════════════════════════

@app.post("/api/chat")
async def chat(msg: ChatMessage):
    try:
        llm = await ask_llm(msg.question, msg.history)
        sql = llm.get("sql")
        explication = llm.get("explication", "")

        if not sql:
            return {"answer": explication, "data": [], "sql": None, "count": 0}

        if FORBIDDEN.search(sql) or not sql.strip().upper().startswith(("SELECT", "WITH")):
            return JSONResponse(status_code=400, content={"detail": "Seules les requêtes SELECT sont autorisées."})

        data = execute_query(sql)
        return {"answer": explication, "data": data, "sql": sql, "count": len(data)}
    except Exception as e:
        print(traceback.format_exc())
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.get("/api/stats")
def get_stats():
    queries = {
        "total_trajets":         "SELECT COUNT(*) AS n FROM trajets WHERE statut='termine'",
        "trajets_en_cours":      "SELECT COUNT(*) AS n FROM trajets WHERE statut='en_cours'",
        "trajets_semaine":       "SELECT COUNT(*) AS n FROM trajets WHERE statut='termine' AND date_heure_depart >= DATE_SUB(NOW(), INTERVAL 7 DAY)",
        "vehicules_actifs":      "SELECT COUNT(*) AS n FROM vehicules WHERE statut='actif'",
        "vehicules_maintenance": "SELECT COUNT(*) AS n FROM vehicules WHERE statut='maintenance'",
        "chauffeurs_dispos":     "SELECT COUNT(*) AS n FROM chauffeurs WHERE disponibilite=TRUE",
        "incidents_ouverts":     "SELECT COUNT(*) AS n FROM incidents WHERE resolu=FALSE",
        "incidents_graves":      "SELECT COUNT(*) AS n FROM incidents WHERE resolu=FALSE AND gravite='grave'",
        "recette_totale":        "SELECT COALESCE(SUM(recette),0) AS n FROM trajets WHERE statut='termine'",
        "recette_mois":          "SELECT COALESCE(SUM(recette),0) AS n FROM trajets WHERE statut='termine' AND MONTH(date_heure_depart)=MONTH(NOW()) AND YEAR(date_heure_depart)=YEAR(NOW())",
    }
    stats = {}
    for key, sql in queries.items():
        r = execute_query(sql)
        v = r[0]["n"] if r else 0
        stats[key] = float(v) if isinstance(v, Decimal) else v
    return stats

@app.get("/api/vehicules")
def get_vehicules():
    return execute_query("""
        SELECT v.*, COALESCE(c.nom,'') AS chauffeur_nom, COALESCE(c.prenom,'') AS chauffeur_prenom
        FROM vehicules v LEFT JOIN chauffeurs c ON c.vehicule_id=v.id ORDER BY v.immatriculation
    """)

@app.get("/api/chauffeurs")
def get_chauffeurs():
    return execute_query("""
        SELECT c.*, COALESCE(v.immatriculation,'') AS vehicule_immat, COALESCE(v.type,'') AS vehicule_type,
               (SELECT COUNT(*) FROM trajets t WHERE t.chauffeur_id=c.id AND t.statut='termine') AS nb_trajets,
               (SELECT COUNT(*) FROM incidents i JOIN trajets t ON i.trajet_id=t.id WHERE t.chauffeur_id=c.id) AS nb_incidents
        FROM chauffeurs c LEFT JOIN vehicules v ON c.vehicule_id=v.id ORDER BY c.nom
    """)

@app.get("/api/trajets/recent")
def get_trajets_recent():
    return execute_query("""
        SELECT t.id, t.statut, t.nb_passagers, t.recette, t.date_heure_depart, t.date_heure_arrivee,
               l.code AS ligne_code, l.nom AS ligne_nom, l.origine, l.destination,
               CONCAT(ch.prenom,' ',ch.nom) AS chauffeur, v.immatriculation, v.type AS vehicule_type,
               (SELECT COUNT(*) FROM incidents i WHERE i.trajet_id=t.id) AS nb_incidents
        FROM trajets t JOIN lignes l ON t.ligne_id=l.id JOIN chauffeurs ch ON t.chauffeur_id=ch.id
        JOIN vehicules v ON t.vehicule_id=v.id ORDER BY t.date_heure_depart DESC LIMIT 20
    """)

@app.get("/api/incidents")
def get_incidents():
    return execute_query("""
        SELECT i.*, t.date_heure_depart, l.code AS ligne_code, l.nom AS ligne_nom,
               CONCAT(ch.prenom,' ',ch.nom) AS chauffeur, v.immatriculation
        FROM incidents i JOIN trajets t ON i.trajet_id=t.id JOIN lignes l ON t.ligne_id=l.id
        JOIN chauffeurs ch ON t.chauffeur_id=ch.id JOIN vehicules v ON t.vehicule_id=v.id
        ORDER BY i.date_incident DESC LIMIT 50
    """)

@app.get("/api/lignes")
def get_lignes():
    lignes = execute_query("SELECT * FROM lignes ORDER BY code")
    tarifs = execute_query("SELECT * FROM tarifs ORDER BY ligne_id, type_client")
    stats  = execute_query("SELECT ligne_id, COUNT(*) AS nb_trajets, COALESCE(SUM(recette),0) AS recette_totale, COALESCE(AVG(nb_passagers),0) AS avg_passagers FROM trajets WHERE statut='termine' GROUP BY ligne_id")
    sm = {s["ligne_id"]: s for s in stats}
    tm: dict = {}
    for t in tarifs: tm.setdefault(t["ligne_id"], []).append(t)
    for l in lignes:
        l["tarifs"] = tm.get(l["id"], [])
        s = sm.get(l["id"], {})
        l["nb_trajets"]     = s.get("nb_trajets", 0)
        l["recette_totale"] = float(s.get("recette_totale", 0) or 0)
        l["avg_passagers"]  = round(float(s.get("avg_passagers", 0) or 0), 1)
    return lignes

@app.get("/health")
def health():
    try:
        execute_query("SELECT 1")
        return {"status": "ok", "db": "connected", "llm": LLM_MODEL}
    except Exception as e:
        return {"status": "error", "db": str(e)}

@app.get("/")
def serve_frontend():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"message": "TranspoBot API — index.html introuvable"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
