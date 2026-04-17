# 🚍 TranspoBot — Gestion de Transport Urbain avec IA

**Licence 3 GLSi — ESP / UCAD**

---

## 📌 Présentation du Projet

**TranspoBot** est une application web intelligente de gestion de transport urbain intégrant un **assistant conversationnel basé sur un Large Language Model (LLM)**.

Le système permet aux gestionnaires d’interroger les données opérationnelles en **langage naturel** afin d’obtenir automatiquement des analyses issues de la base de données.

Projet réalisé dans le cadre du cours :

> **Intégration de l’IA dans les Systèmes d’Information**

---

## 🎯 Objectifs

* Concevoir une architecture complète SI + IA
* Développer une API backend professionnelle
* Implémenter un système **Text-to-SQL**
* Sécuriser les requêtes générées par IA
* Déployer une application accessible en ligne

---

## 🧠 Fonctionnalités Principales

### ✅ Gestion classique

* Liste des véhicules
* Gestion des chauffeurs
* Consultation des trajets récents
* Tableau de bord KPI

### 🤖 Assistant IA Conversationnel

* Questions en français ou anglais
* Génération automatique de requêtes SQL
* Affichage dynamique des résultats
* Sécurité : uniquement requêtes `SELECT`

**Exemples :**

* Combien de trajets cette semaine ?
* Quel chauffeur a le plus d'incidents ?
* Quelle est la recette totale ?

---

## 🏗 Architecture Technique

| Composant                 | Technologie             |
| ------------------------- | ----------------------- |
| Backend                   | FastAPI (Python)        |
| Base de données           | MySQL 8                 |
| Intelligence Artificielle | OpenAI / Groq API       |
| Frontend                  | HTML / CSS / JavaScript |
| API REST                  | JSON                    |
| Déploiement               | Render                  |
| Versioning                | GitHub                  |

---

## ⚙️ Architecture du Système

Utilisateur
⬇
Interface Web (Dashboard + Chat IA)
⬇
API FastAPI
⬇
LLM (Text-to-SQL)
⬇
Validation Sécurité SQL
⬇
Base MySQL
⬇
Résultats → Interface Web

---

## 🗄 Base de Données

Tables principales :

* `vehicules`
* `chauffeurs`
* `lignes`
* `tarifs`
* `trajets`
* `incidents`

Le script complet est disponible dans :

```
schema_transpobot_enrichi.sql
```

---

## 🚀 Installation Locale

### 1️⃣ Cloner le projet

```bash
git clone https://github.com/nafissatou5/transpobot.git
cd transpobot
```

### 2️⃣ Créer environnement Python

```bash
python -m venv venv
source venv/Scripts/activate
```

### 3️⃣ Installer dépendances

```bash
pip install -r requirements.txt
```

### 4️⃣ Configurer variables d'environnement

Créer `.env` :

```
DB_HOST=
DB_USER=
DB_PASSWORD=
DB_NAME=

OPENAI_API_KEY=
LLM_MODEL=gpt-4o-mini
```

---

### 5️⃣ Lancer l’application

```bash
python -m uvicorn app:app --reload
```

Application :

```
http://localhost:8000
```

---

## 🌍 Déploiement Render

1. Connecter le dépôt GitHub à Render
2. Créer un **Web Service**
3. Ajouter variables d'environnement
4. Start Command :

```
python -m uvicorn app:app --host 0.0.0.0 --port 10000
```

5. Importer le script SQL dans la base MySQL distante
6. Tester :

```
/health
/api/stats
```

---

## 🔒 Sécurité IA

* Blocage INSERT / UPDATE / DELETE
* Validation SQL automatique
* Prompt système sécurisé
* Limite `LIMIT 100`
* Clés API protégées via `.env`

---

## 🧪 API Principales

| Endpoint              | Description      |
| --------------------- | ---------------- |
| `/api/chat`           | Assistant IA     |
| `/api/stats`          | KPIs Dashboard   |
| `/api/vehicules`      | Liste véhicules  |
| `/api/chauffeurs`     | Liste chauffeurs |
| `/api/trajets/recent` | Trajets récents  |
| `/api/incidents`      | Incidents        |
| `/health`             | Test serveur     |

---

## ⚠️ Difficultés Rencontrées

| Domaine     | Problème                    | Solution                    |
| ----------- | --------------------------- | --------------------------- |
| Git         | Conflits rebase             | Force push contrôlé         |
| IA          | Mauvaise config OpenAI/Groq | Correction base_url         |
| Déploiement | Erreur 500                  | Variables env + DB distante |
| Sécurité    | Exposition clés API         | `.gitignore` + `.env`       |

---

## 📦 Livrables

* ✅ Application déployée
* ✅ Chat IA fonctionnel
* ✅ Code source GitHub
* ✅ Script SQL
* ✅ Rapport PDF
* ✅ Présentation PPT

---

## 👩‍💻 Auteurs

Projet réalisé par :

**Nafissatou Faye**
**Mareme Tine**
**Abdoul Wahab Sall**
**Anta Diama Kama**
Licence 3 GLSi — ESP UCAD

---

## 🎓 Encadrement

**Pr. Ahmath Bamba MBACKE**
ESP — Université Cheikh Anta Diop de Dakar

---

## 📜 Licence

Projet académique — Usage pédagogique uniquement.
