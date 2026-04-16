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
from typing import List, Optional

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

if not LLM_API_KEY:
    print("⚠️ WARNING: OPENAI_API_KEY est vide")

# ── Schéma BDD injecté dans le prompt ─────────────────────────────────────
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
Tu es TranspoBot.

{DB_SCHEMA}

RÈGLES :
1. UNIQUEMENT SELECT
2. JSON strict: {{"sql": "...", "explication": "..."}}
3. sinon {{"sql": null, "explication": "..."}}
4. LIMIT 100 obligatoire
"""

# ── DB ─────────────────────────────────────────────────────────────────────
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

# ── Sécurité SQL ───────────────────────────────────────────────────────────
FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE|CALL)\b",
    re.IGNORECASE
)

def is_safe_query(sql: str) -> bool:
    if not sql or not sql.strip():
        return False
    if FORBIDDEN.search(sql):
        return False
    return sql.strip().upper().startswith(("SELECT", "WITH"))

# ── LLM ─────────────────────────────────────────────────────────────────────
async def ask_llm(question: str, history: Optional[List] = None) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-6:])
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
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=response.text)
        content = response.json()["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise HTTPException(status_code=500, detail="JSON LLM invalide")

# ── MODELE ──────────────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    question: str
    history: Optional[List] = []

# ══ ROUTES ══════════════════════════════════════════════════════════════════

@app.post("/api/chat")
async def chat(msg: ChatMessage):
    try:
        llm_response = await ask_llm(msg.question, msg.history or [])
        sql = llm_response.get("sql")
        explication = llm_response.get("explication", "")
        if not sql:
            return {"answer": explication, "data": [], "sql": None, "count": 0}
        if not is_safe_query(sql):
            raise HTTPException(status_code=400, detail="Requête SQL interdite")
        data = execute_query(sql)
        return {"answer": explication, "data": data, "sql": sql, "count": len(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
def get_stats():
    queries = {
        "total_trajets":        "SELECT COUNT(*) AS n FROM trajets WHERE statut='termine'",
        "trajets_semaine":      "SELECT COUNT(*) AS n FROM trajets WHERE statut='termine' AND date_heure_depart >= DATE_SUB(NOW(), INTERVAL 7 DAY)",
        "trajets_en_cours":     "SELECT COUNT(*) AS n FROM trajets WHERE statut='en_cours'",
        "vehicules_actifs":     "SELECT COUNT(*) AS n FROM vehicules WHERE statut='actif'",
        "vehicules_maintenance":"SELECT COUNT(*) AS n FROM vehicules WHERE statut='maintenance'",
        "incidents_ouverts":    "SELECT COUNT(*) AS n FROM incidents WHERE resolu=0",
        "incidents_graves":     "SELECT COUNT(*) AS n FROM incidents WHERE resolu=0 AND gravite='grave'",
        "recette_totale":       "SELECT COALESCE(SUM(recette),0) AS n FROM trajets WHERE statut='termine'",
        "recette_mois":         "SELECT COALESCE(SUM(recette),0) AS n FROM trajets WHERE statut='termine' AND MONTH(date_heure_depart)=MONTH(NOW()) AND YEAR(date_heure_depart)=YEAR(NOW())",
        "chauffeurs_dispos":    "SELECT COUNT(*) AS n FROM chauffeurs WHERE disponibilite=1",
    }
    stats = {}
    for k, q in queries.items():
        r = execute_query(q)
        stats[k] = r[0]["n"] if r else 0
    return stats


@app.get("/api/trajets/recent")
def get_trajets_recent():
    sql = """
        SELECT t.id, t.statut, t.date_heure_depart, t.date_heure_arrivee,
               t.nb_passagers, t.recette,
               l.code AS ligne_code, l.nom AS ligne_nom,
               l.origine, l.destination,
               CONCAT(c.prenom, ' ', c.nom) AS chauffeur,
               v.immatriculation,
               (SELECT COUNT(*) FROM incidents i WHERE i.trajet_id = t.id) AS nb_incidents
        FROM trajets t
        JOIN lignes l ON t.ligne_id = l.id
        JOIN chauffeurs c ON t.chauffeur_id = c.id
        JOIN vehicules v ON t.vehicule_id = v.id
        ORDER BY t.date_heure_depart DESC
        LIMIT 20
    """
    return execute_query(sql)


@app.get("/api/vehicules")
def get_vehicules():
    sql = """
        SELECT v.*,
               c.nom AS chauffeur_nom, c.prenom AS chauffeur_prenom
        FROM vehicules v
        LEFT JOIN chauffeurs c ON c.vehicule_id = v.id
        ORDER BY v.statut, v.immatriculation
    """
    return execute_query(sql)


@app.get("/api/chauffeurs")
def get_chauffeurs():
    sql = """
        SELECT c.*,
               COALESCE(v.immatriculation, '—') AS vehicule_immat,
               COALESCE(v.type, '—')            AS vehicule_type,
               (SELECT COUNT(*) FROM trajets t WHERE t.chauffeur_id = c.id) AS nb_trajets,
               (SELECT COUNT(*) FROM incidents i
                JOIN trajets t ON i.trajet_id = t.id
                WHERE t.chauffeur_id = c.id) AS nb_incidents
        FROM chauffeurs c
        LEFT JOIN vehicules v ON c.vehicule_id = v.id
        ORDER BY c.nom, c.prenom
    """
    return execute_query(sql)


@app.get("/api/incidents")
def get_incidents():
    sql = """
        SELECT i.*,
               l.code AS ligne_code, l.nom AS ligne_nom,
               CONCAT(c.prenom, ' ', c.nom) AS chauffeur,
               v.immatriculation
        FROM incidents i
        JOIN trajets t  ON i.trajet_id  = t.id
        JOIN lignes l   ON t.ligne_id   = l.id
        JOIN chauffeurs c ON t.chauffeur_id = c.id
        JOIN vehicules v  ON t.vehicule_id  = v.id
        ORDER BY i.date_incident DESC
        LIMIT 50
    """
    return execute_query(sql)


@app.get("/api/lignes")
def get_lignes():
    lignes = execute_query("SELECT * FROM lignes ORDER BY code")
    for ligne in lignes:
        lid = ligne["id"]
        ligne["tarifs"] = execute_query(
            f"SELECT type_client, prix FROM tarifs WHERE ligne_id={lid}"
        )
        stats = execute_query(f"""
            SELECT COUNT(*) AS nb_trajets,
                   COALESCE(SUM(recette),0) AS recette_totale,
                   COALESCE(AVG(nb_passagers),0) AS avg_passagers
            FROM trajets WHERE ligne_id={lid} AND statut='termine'
        """)
        if stats:
            ligne["nb_trajets"]    = stats[0]["nb_trajets"]
            ligne["recette_totale"]= stats[0]["recette_totale"]
            ligne["avg_passagers"] = round(stats[0]["avg_passagers"] or 0)
        else:
            ligne["nb_trajets"] = ligne["recette_totale"] = ligne["avg_passagers"] = 0
    return lignes


# ── HEALTH ──────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    try:
        execute_query("SELECT 1")
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

# ── FRONTEND ───────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

@app.get("/")
def home():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))

@app.get("/chat")
def chat_page():
    return FileResponse(os.path.join(BASE_DIR, "static", "chat.html"))

# ── RUN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)