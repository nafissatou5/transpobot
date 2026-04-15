"""
TranspoBot — Backend FastAPI
Groq + MySQL — Version debug robuste
"""
import os, re, json, traceback
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

import httpx
import mysql.connector
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# ── Lecture manuelle du .env (corrige bug Windows dernière ligne sans \n) ──
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as _f:
        for _line in _f.read().splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ[_k.strip()] = _v.strip()

LLM_API_KEY  = os.environ.get("GROQ_API_KEY", "").strip()
LLM_MODEL    = os.environ.get("LLM_MODEL", "llama3-8b-8192").strip()
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1").strip()

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST",     "localhost"),
    "user":     os.environ.get("DB_USER",     "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME",     "transpobot"),
    "charset":  "utf8mb4",
}

print(f"[CONFIG] KEY={LLM_API_KEY[:12] if LLM_API_KEY else 'VIDE'}... MODEL={LLM_MODEL}")

SYSTEM_PROMPT = """Tu es TranspoBot, assistant Text-to-SQL pour une compagnie de transport sénégalaise.

BASE MySQL (base: transpobot) :
vehicules(id, immatriculation, type ENUM['bus','minibus','taxi'], capacite, statut ENUM['actif','maintenance','hors_service'], kilometrage, date_acquisition)
chauffeurs(id, nom, prenom, telephone, numero_permis, categorie_permis, disponibilite BOOLEAN, vehicule_id FK→vehicules, date_embauche)
lignes(id, code, nom, origine, destination, distance_km, duree_minutes)
tarifs(id, ligne_id FK→lignes, type_client ENUM['normal','etudiant','senior'], prix)
trajets(id, ligne_id FK→lignes, chauffeur_id FK→chauffeurs, vehicule_id FK→vehicules, date_heure_depart DATETIME, date_heure_arrivee DATETIME, statut ENUM['planifie','en_cours','termine','annule'], nb_passagers, recette)
incidents(id, trajet_id FK→trajets, type ENUM['panne','accident','retard','autre'], description, gravite ENUM['faible','moyen','grave'], date_incident DATETIME, resolu BOOLEAN)

RÈGLES :
1. SELECT uniquement. Jamais INSERT/UPDATE/DELETE/DROP.
2. Réponds UNIQUEMENT en JSON valide sans markdown ni backticks.
3. Format : {"sql":"SELECT ...","explication":"...en français"}
4. Hors BDD : {"sql":null,"explication":"réponse"}
5. LIMIT 100. Valeurs sans accents : 'termine','planifie','en_cours','annule'.
6. Cette semaine : date_heure_depart >= DATE_SUB(NOW(), INTERVAL 7 DAY)
7. Ce mois : MONTH(col)=MONTH(NOW()) AND YEAR(col)=YEAR(NOW())

EXEMPLES :
Q: "Combien de trajets cette semaine ?"
{"sql":"SELECT COUNT(*) AS nb FROM trajets WHERE date_heure_depart >= DATE_SUB(NOW(), INTERVAL 7 DAY) AND statut='termine'","explication":"Trajets terminés cette semaine."}
Q: "Véhicules en maintenance ?"
{"sql":"SELECT immatriculation, type, kilometrage FROM vehicules WHERE statut='maintenance'","explication":"Véhicules en maintenance."}
Q: "Quel chauffeur a le plus d incidents ?"
{"sql":"SELECT c.nom, c.prenom, COUNT(i.id) AS nb FROM incidents i JOIN trajets t ON i.trajet_id=t.id JOIN chauffeurs c ON t.chauffeur_id=c.id GROUP BY c.id ORDER BY nb DESC LIMIT 1","explication":"Chauffeur avec le plus d incidents."}
"""

app = FastAPI(title="TranspoBot")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ChatMessage(BaseModel):
    question: str
    history: Optional[List] = []

FORBIDDEN = re.compile(r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b', re.IGNORECASE)

def clean_val(v):
    if isinstance(v, datetime): return v.isoformat()
    if isinstance(v, Decimal):  return float(v)
    if isinstance(v, bytes):    return v.decode("utf-8", errors="replace")
    return v

def execute_query(sql: str):
    conn = mysql.connector.connect(**DB_CONFIG)
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(sql)
        rows = cur.fetchall()
        return [{k: clean_val(v) for k, v in row.items()} for row in rows]
    finally:
        cur.close(); conn.close()

async def call_groq(question: str, history: list = None) -> dict:
    if not LLM_API_KEY:
        raise ValueError("GROQ_API_KEY vide — vérifie .env")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        for h in (history[-6:]):
            if isinstance(h, dict) and h.get("role") and h.get("content"):
                messages.append({"role": h["role"], "content": str(h["content"])})
    messages.append({"role": "user", "content": question})

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": LLM_MODEL, "messages": messages, "temperature": 0},
        )

    print(f"[GROQ] status={resp.status_code}")
    if resp.status_code != 200:
        print(f"[GROQ] error={resp.text[:300]}")
        resp.raise_for_status()

    content = resp.json()["choices"][0]["message"]["content"].strip()
    print(f"[GROQ] raw={content[:300]}")

    # Nettoyer markdown
    content = re.sub(r"```(?:json)?", "", content).strip().strip("`").strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', content, re.DOTALL)
        if m:
            try: return json.loads(m.group())
            except: pass
    return {"sql": None, "explication": content}

# ══ ROUTES ════════════════════════════════

@app.post("/api/chat")
async def chat(msg: ChatMessage):
    try:
        print(f"[CHAT] question={msg.question}")
        result = await call_groq(msg.question, msg.history)
        sql  = result.get("sql")
        expl = result.get("explication", "")

        if not sql:
            return {"answer": expl, "data": [], "sql": None, "count": 0}

        if FORBIDDEN.search(sql) or not sql.strip().upper().startswith(("SELECT","WITH")):
            return JSONResponse(400, {"detail": "Seules les requêtes SELECT sont autorisées."})

        data = execute_query(sql)
        print(f"[CHAT] rows={len(data)}")
        return {"answer": expl, "data": data, "sql": sql, "count": len(data)}

    except Exception as e:
        print(f"[ERREUR]\n{traceback.format_exc()}")
        return JSONResponse(500, {"detail": str(e)})

@app.get("/api/stats")
def get_stats():
    qs = {
        "total_trajets":         "SELECT COUNT(*) AS n FROM trajets WHERE statut='termine'",
        "trajets_en_cours":      "SELECT COUNT(*) AS n FROM trajets WHERE statut='en_cours'",
        "trajets_semaine":       "SELECT COUNT(*) AS n FROM trajets WHERE statut='termine' AND date_heure_depart>=DATE_SUB(NOW(),INTERVAL 7 DAY)",
        "vehicules_actifs":      "SELECT COUNT(*) AS n FROM vehicules WHERE statut='actif'",
        "vehicules_maintenance": "SELECT COUNT(*) AS n FROM vehicules WHERE statut='maintenance'",
        "chauffeurs_dispos":     "SELECT COUNT(*) AS n FROM chauffeurs WHERE disponibilite=TRUE",
        "incidents_ouverts":     "SELECT COUNT(*) AS n FROM incidents WHERE resolu=FALSE",
        "incidents_graves":      "SELECT COUNT(*) AS n FROM incidents WHERE resolu=FALSE AND gravite='grave'",
        "recette_totale":        "SELECT COALESCE(SUM(recette),0) AS n FROM trajets WHERE statut='termine'",
        "recette_mois":          "SELECT COALESCE(SUM(recette),0) AS n FROM trajets WHERE statut='termine' AND MONTH(date_heure_depart)=MONTH(NOW()) AND YEAR(date_heure_depart)=YEAR(NOW())",
    }
    out = {}
    for k, sql in qs.items():
        r = execute_query(sql)
        v = r[0]["n"] if r else 0
        out[k] = float(v) if isinstance(v, Decimal) else v
    return out

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
        SELECT t.id, t.statut, t.nb_passagers, t.recette,
               t.date_heure_depart, t.date_heure_arrivee,
               l.code AS ligne_code, l.nom AS ligne_nom, l.origine, l.destination,
               CONCAT(ch.prenom,' ',ch.nom) AS chauffeur,
               v.immatriculation, v.type AS vehicule_type,
               (SELECT COUNT(*) FROM incidents i WHERE i.trajet_id=t.id) AS nb_incidents
        FROM trajets t
        JOIN lignes l ON t.ligne_id=l.id
        JOIN chauffeurs ch ON t.chauffeur_id=ch.id
        JOIN vehicules v ON t.vehicule_id=v.id
        ORDER BY t.date_heure_depart DESC LIMIT 20
    """)

@app.get("/api/incidents")
def get_incidents():
    return execute_query("""
        SELECT i.*, t.date_heure_depart,
               l.code AS ligne_code, l.nom AS ligne_nom,
               CONCAT(ch.prenom,' ',ch.nom) AS chauffeur, v.immatriculation
        FROM incidents i
        JOIN trajets t ON i.trajet_id=t.id
        JOIN lignes l ON t.ligne_id=l.id
        JOIN chauffeurs ch ON t.chauffeur_id=ch.id
        JOIN vehicules v ON t.vehicule_id=v.id
        ORDER BY i.date_incident DESC LIMIT 50
    """)

@app.get("/api/lignes")
def get_lignes():
    lignes = execute_query("SELECT * FROM lignes ORDER BY code")
    tarifs = execute_query("SELECT * FROM tarifs ORDER BY ligne_id, type_client")
    stats  = execute_query("""
        SELECT ligne_id, COUNT(*) AS nb_trajets,
               COALESCE(SUM(recette),0) AS recette_totale,
               COALESCE(AVG(nb_passagers),0) AS avg_passagers
        FROM trajets WHERE statut='termine' GROUP BY ligne_id
    """)
    sm = {s["ligne_id"]: s for s in stats}
    tm: dict = {}
    for t in tarifs: tm.setdefault(t["ligne_id"], []).append(t)
    for l in lignes:
        l["tarifs"]         = tm.get(l["id"], [])
        s = sm.get(l["id"], {})
        l["nb_trajets"]     = s.get("nb_trajets", 0)
        l["recette_totale"] = float(s.get("recette_totale", 0) or 0)
        l["avg_passagers"]  = round(float(s.get("avg_passagers", 0) or 0), 1)
    return lignes

@app.get("/health")
def health():
    try:
        execute_query("SELECT 1")
        return {"status": "ok", "db": "connected", "llm": LLM_MODEL,
                "key_ok": bool(LLM_API_KEY)}
    except Exception as e:
        return {"status": "error", "db": str(e)}

@app.get("/")
def root():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"message": "TranspoBot API OK"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
