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

IMPORTANT: Les valeurs ENUM sont sans accents. Utiliser 'termine' (pas 'terminé'),
'planifie', 'en_cours', 'annule', 'faible', 'moyen', 'grave', 'panne', 'accident', 'retard'.
"""

SYSTEM_PROMPT = f"""Tu es TranspoBot, l'assistant intelligent d'une compagnie de transport urbain sénégalaise.
Tu aides les gestionnaires à interroger la base de données MySQL en langage naturel (français ou anglais).

{DB_SCHEMA}

RÈGLES ABSOLUES :
1. Génère UNIQUEMENT des requêtes SELECT. Jamais INSERT, UPDATE, DELETE, DROP, ALTER, CREATE.
2. Réponds TOUJOURS en JSON valide avec EXACTEMENT ce format :
   {{"sql": "SELECT ...", "explication": "Ce que fait la requête en langage naturel"}}
3. Si la question ne peut pas être répondue par SQL (question générale, hors domaine), réponds :
   {{"sql": null, "explication": "Ta réponse en langage naturel"}}
4. Utilise toujours LIMIT 100 maximum pour éviter des résultats trop longs.
5. Utilise des alias clairs : c.nom AS chauffeur_nom, v.immatriculation, etc.
6. Pour les dates relatives : utilise DATE_SUB(NOW(), INTERVAL X DAY/MONTH/YEAR).
7. Pour "cette semaine" : WHERE date_heure_depart >= DATE_SUB(NOW(), INTERVAL 7 DAY).
8. Pour "ce mois" : WHERE MONTH(col) = MONTH(NOW()) AND YEAR(col) = YEAR(NOW()).
9. Ne génère jamais de JSON mal formé. Le champ "sql" doit être une chaîne SQL valide ou null.

EXEMPLES FEW-SHOT :
Q: "Combien de trajets cette semaine ?"
R: {{"sql": "SELECT COUNT(*) AS nb_trajets FROM trajets WHERE date_heure_depart >= DATE_SUB(NOW(), INTERVAL 7 DAY) AND statut='termine'", "explication": "Nombre de trajets terminés au cours des 7 derniers jours."}}

Q: "Quel chauffeur a le plus d'incidents ce mois ?"
R: {{"sql": "SELECT c.nom, c.prenom, COUNT(i.id) AS nb_incidents FROM incidents i JOIN trajets t ON i.trajet_id=t.id JOIN chauffeurs c ON t.chauffeur_id=c.id WHERE MONTH(i.date_incident)=MONTH(NOW()) AND YEAR(i.date_incident)=YEAR(NOW()) GROUP BY c.id ORDER BY nb_incidents DESC LIMIT 1", "explication": "Le chauffeur avec le plus d'incidents enregistrés ce mois-ci."}}

Q: "Quels véhicules sont en maintenance ?"
R: {{"sql": "SELECT immatriculation, type, kilometrage, date_acquisition FROM vehicules WHERE statut='maintenance'", "explication": "Liste des véhicules actuellement en maintenance."}}

Q: "Quelle est la recette totale ?"
R: {{"sql": "SELECT COALESCE(SUM(recette), 0) AS recette_totale FROM trajets WHERE statut='termine'", "explication": "Recette totale de tous les trajets terminés en FCFA."}}
"""

# ── Connexion MySQL ─────────────────────────────────────────────────────────
def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def execute_query(sql: str):
    """Exécute une requête SELECT et retourne les résultats."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql)
        results = cursor.fetchall()
        # Convertir les types non-sérialisables (datetime, Decimal)
        cleaned = []
        for row in results:
            clean_row = {}
            for k, v in row.items():
                if isinstance(v, datetime):
                    clean_row[k] = v.isoformat()
                elif hasattr(v, '__float__'):
                    clean_row[k] = float(v)
                else:
                    clean_row[k] = v
            cleaned.append(clean_row)
        return cleaned
    finally:
        cursor.close()
        conn.close()

# ── Sécurité : vérifier que la requête est bien un SELECT ──────────────────
FORBIDDEN = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE|CALL)\b',
    re.IGNORECASE
)

def is_safe_query(sql: str) -> bool:
    """Vérifie que la requête est uniquement SELECT."""
    if not sql or not sql.strip():
        return False
    if FORBIDDEN.search(sql):
        return False
    stripped = sql.strip().upper()
    return stripped.startswith("SELECT") or stripped.startswith("WITH")

# ── Appel LLM ───────────────────────────────────────────────────────────────
# ── Appel LLM (Version corrigée pour Groq) ──────────────────────────────────
async def ask_llm(question: str, history: list = None) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        for h in history[-6:]:
            messages.append(h)
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
            print(f"Erreur API : {response.text}")
            response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]
        
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Sécurité au cas où le modèle ajoute du texte avant/après le JSON
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError("Réponse LLM invalide : JSON non parseable")

# ── Modèles Pydantic ────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    question: str
    history: list = []

# ══ ROUTES API ════════════════════════════════════════════════════════════════

@app.post("/api/chat")
async def chat(msg: ChatMessage):
    """Point d'entrée principal : question → SQL → résultats."""
    try:
        llm_response = await ask_llm(msg.question, msg.history)
        sql = llm_response.get("sql")
        explication = llm_response.get("explication", "")

        if not sql:
            return {"answer": explication, "data": [], "sql": None, "count": 0}

        if not is_safe_query(sql):
            raise HTTPException(
                status_code=400,
                detail="Requête non autorisée : seules les requêtes SELECT sont permises."
            )

        data = execute_query(sql)
        return {
            "answer": explication,
            "data": data,
            "sql": sql,
            "count": len(data),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur : {str(e)}")


@app.get("/api/stats")
def get_stats():
    """Tableau de bord — KPIs principaux."""
    queries = {
        "total_trajets":      "SELECT COUNT(*) AS n FROM trajets WHERE statut='termine'",
        "trajets_en_cours":   "SELECT COUNT(*) AS n FROM trajets WHERE statut='en_cours'",
        "trajets_semaine":    "SELECT COUNT(*) AS n FROM trajets WHERE statut='termine' AND date_heure_depart >= DATE_SUB(NOW(), INTERVAL 7 DAY)",
        "vehicules_actifs":   "SELECT COUNT(*) AS n FROM vehicules WHERE statut='actif'",
        "vehicules_maintenance": "SELECT COUNT(*) AS n FROM vehicules WHERE statut='maintenance'",
        "chauffeurs_dispos":  "SELECT COUNT(*) AS n FROM chauffeurs WHERE disponibilite=TRUE",
        "incidents_ouverts":  "SELECT COUNT(*) AS n FROM incidents WHERE resolu=FALSE",
        "incidents_graves":   "SELECT COUNT(*) AS n FROM incidents WHERE resolu=FALSE AND gravite='grave'",
        "recette_totale":     "SELECT COALESCE(SUM(recette), 0) AS n FROM trajets WHERE statut='termine'",
        "recette_mois":       "SELECT COALESCE(SUM(recette), 0) AS n FROM trajets WHERE statut='termine' AND MONTH(date_heure_depart)=MONTH(NOW()) AND YEAR(date_heure_depart)=YEAR(NOW())",
    }
    stats = {}
    for key, sql in queries.items():
        result = execute_query(sql)
        val = result[0]["n"] if result else 0
        stats[key] = float(val) if hasattr(val, '__float__') else val
    return stats


@app.get("/api/vehicules")
def get_vehicules():
    """Liste complète des véhicules."""
    return execute_query("""
        SELECT v.*, 
               COALESCE(c.nom, '—') AS chauffeur_nom,
               COALESCE(c.prenom, '') AS chauffeur_prenom
        FROM vehicules v
        LEFT JOIN chauffeurs c ON c.vehicule_id = v.id
        ORDER BY v.immatriculation
    """)


@app.get("/api/chauffeurs")
def get_chauffeurs():
    """Liste complète des chauffeurs avec leur véhicule."""
    return execute_query("""
        SELECT c.*, 
               COALESCE(v.immatriculation, '—') AS vehicule_immat,
               COALESCE(v.type, '') AS vehicule_type,
               (SELECT COUNT(*) FROM trajets t WHERE t.chauffeur_id = c.id AND t.statut='termine') AS nb_trajets,
               (SELECT COUNT(*) FROM incidents i JOIN trajets t ON i.trajet_id=t.id WHERE t.chauffeur_id=c.id) AS nb_incidents
        FROM chauffeurs c
        LEFT JOIN vehicules v ON c.vehicule_id = v.id
        ORDER BY c.nom
    """)


@app.get("/api/trajets/recent")
def get_trajets_recent():
    """20 derniers trajets avec toutes les informations."""
    return execute_query("""
        SELECT t.id, t.statut, t.nb_passagers, t.recette,
               t.date_heure_depart, t.date_heure_arrivee,
               l.code AS ligne_code, l.nom AS ligne_nom,
               l.origine, l.destination,
               CONCAT(ch.prenom, ' ', ch.nom) AS chauffeur,
               v.immatriculation, v.type AS vehicule_type,
               (SELECT COUNT(*) FROM incidents i WHERE i.trajet_id = t.id) AS nb_incidents
        FROM trajets t
        JOIN lignes l     ON t.ligne_id     = l.id
        JOIN chauffeurs ch ON t.chauffeur_id = ch.id
        JOIN vehicules v   ON t.vehicule_id  = v.id
        ORDER BY t.date_heure_depart DESC
        LIMIT 20
    """)


@app.get("/api/incidents")
def get_incidents():
    """Liste des incidents avec détails du trajet."""
    return execute_query("""
        SELECT i.*, 
               t.date_heure_depart,
               l.code AS ligne_code, l.nom AS ligne_nom,
               CONCAT(ch.prenom, ' ', ch.nom) AS chauffeur,
               v.immatriculation
        FROM incidents i
        JOIN trajets t     ON i.trajet_id    = t.id
        JOIN lignes l      ON t.ligne_id     = l.id
        JOIN chauffeurs ch ON t.chauffeur_id = ch.id
        JOIN vehicules v   ON t.vehicule_id  = v.id
        ORDER BY i.date_incident DESC
        LIMIT 50
    """)


@app.get("/api/lignes")
def get_lignes():
    """Liste des lignes avec leurs tarifs et statistiques."""
    lignes = execute_query("SELECT * FROM lignes ORDER BY code")
    tarifs = execute_query("SELECT * FROM tarifs ORDER BY ligne_id, type_client")
    stats  = execute_query("""
        SELECT ligne_id,
               COUNT(*) AS nb_trajets,
               COALESCE(SUM(recette), 0) AS recette_totale,
               COALESCE(AVG(nb_passagers), 0) AS avg_passagers
        FROM trajets WHERE statut='termine'
        GROUP BY ligne_id
    """)
    stats_map = {s["ligne_id"]: s for s in stats}
    tarifs_map: dict = {}
    for t in tarifs:
        tarifs_map.setdefault(t["ligne_id"], []).append(t)
    for ligne in lignes:
        ligne["tarifs"] = tarifs_map.get(ligne["id"], [])
        s = stats_map.get(ligne["id"], {})
        ligne["nb_trajets"]    = s.get("nb_trajets", 0)
        ligne["recette_totale"] = float(s.get("recette_totale", 0))
        ligne["avg_passagers"] = round(float(s.get("avg_passagers", 0)), 1)
    return lignes


@app.get("/health")
def health():
    """Vérification que l'API est en ligne."""
    try:
        execute_query("SELECT 1")
        return {"status": "ok", "app": "TranspoBot", "db": "connected"}
    except Exception as e:
        return {"status": "error", "app": "TranspoBot", "db": str(e)}


# ── Servir le frontend ──────────────────────────────────────────────────────
if os.path.exists("index.html"):
    @app.get("/")
    def serve_frontend():
        return FileResponse("index.html")

# ── Lancement ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
