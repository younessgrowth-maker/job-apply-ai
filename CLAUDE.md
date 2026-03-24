# CLAUDE.md — Job Apply AI

## Contexte projet
SaaS B2C d'automatisation de candidatures d'emploi propulsé par des agents IA.
L'utilisateur uploade son CV → il reçoit des candidatures personnalisées envoyées automatiquement sur les plateformes d'emploi et par email direct aux recruteurs.

**Repo GitHub** : https://github.com/younessgrowth-maker/job-apply-ai
**Développeur** : Youness EL YACOUBI — étudiant ING4 Data & IA (ECE Paris), Data Analyst en apprentissage (SFR). Stack habituel : Python, R, BigQuery, Jupyter.
**Budget** : Claude Max + ChatGPT 25€/mois. VPS OVH ~5€/mois. APIs gratuites/freemium au maximum.

---

## Architecture — Système multi-agents

### Agents spécialisés (pas un agent unique)

| Agent | Rôle | Tech principale |
|-------|------|-----------------|
| **CV Optimizer** | Analyse, restructure, optimise le CV (mots-clés ATS, mise en forme) | LLM (Claude API) + pdfplumber |
| **Scraper/Matcher** | Scrape les offres d'emploi, normalise, score par pertinence | Python (Playwright) + SerpAPI + LLM pour scoring |
| **Cover Letter Writer** | Génère une lettre de motivation unique par offre | LLM (Claude API) |
| **Quality Reviewer** | Relit et valide la lettre avant envoi | LLM (prompt de critique) |
| **Applicator** | Postule automatiquement via les formulaires | Playwright (peu de LLM) |
| **Outreach Agent** | Emails personnalisés aux recruteurs + séquences de relance | LLM + Gmail API |
| **Orchestrateur** | Coordonne le pipeline complet, gère l'état des candidatures | n8n (self-hosted) |

### Pipeline principal
```
Upload CV (PDF/Word)
  → Agent CV Optimizer (extraction + optimisation ATS)
  → Profil structuré (JSON) stocké en BDD
  → Agent Scraper (SerpAPI / Google Jobs / scraping direct)
  → Matching & scoring des offres vs profil
  → Filtrage (critères utilisateur : poste, lieu, contrat, XP, secteur)
  → Agent Cover Letter Writer (1 lettre / offre retenue)
  → Agent Quality Reviewer (validation)
  → Agent Applicator (dépôt candidature) + Agent Outreach (email recruteurs)
  → Dashboard de suivi (envoyée / vue / réponse reçue)
```

---

## Stack technique

### Backend & orchestration
- **Langage** : Python 3.11+
- **Orchestration** : n8n (self-hosted, Docker) — workflows visuels reliant les agents
- **LLM** : API Claude (Anthropic) pour la rédaction, modèle moins cher pour le scoring
- **BDD** : PostgreSQL (ou SQLite pour le MVP)
- **File d'attente** : Redis + Celery (si besoin d'async)

### Scraping & données
- **Google Jobs** via SerpAPI (plan gratuit 100 req/mois, puis ~50$/mois)
- **JSearch** (RapidAPI) et **Adzuna API** comme alternatives gratuites
- **Playwright** pour le scraping direct (dernier recours)
- Anti-détection : rotation proxies, délais aléatoires 2-8s, rotation User-Agents
- LinkedIn : pas de scraping direct (risque ban), utiliser Google Jobs comme proxy

### Base contacts recruteurs (alternative Apollo)
- **Hunter.io** (25 req/mois gratuit) pour emails professionnels
- **Snov.io** / **Dropcontact** comme alternatives
- **Pappers.fr** / **Societeinfo.com** pour infos entreprises FR
- Déduction de patterns email (prenom.nom@entreprise.com)
- Validation email : ZeroBounce / Reoon
- Enrichissement progressif par effet réseau (chaque utilisateur enrichit la base)

### Frontend (phase ultérieure)
- Dashboard : Streamlit (MVP rapide) puis React (production)
- Landing page : template HTML ou Framer

### Email outreach
- Gmail API via n8n
- Séquences de relance automatisées
- Personnalisation par LLM

---

## Contraintes légales à respecter

### RGPD
- Consentement explicite de l'utilisateur pour traiter son CV
- Intérêt légitime pour outreach B2B (emails pro) + opt-out obligatoire
- Hébergement données en UE (OVH, Scaleway)
- Registre des traitements à tenir

### CGU plateformes
- LinkedIn, Indeed, HelloWork interdisent le scraping dans leurs CGU
- Mitigation : utiliser API officielles et agrégateurs en priorité
- Candidatures auto détectées et bannies par certaines plateformes (LinkedIn agressif)
- Mandat clair de l'utilisateur dans les CGU/CGV (agit comme mandataire)

### À faire
- CGU + politique de confidentialité par avocat spécialisé tech/RGPD (~500-1000€)

---

## Plan de développement

### Phase 1 — MVP Core (Semaines 1-6) ← ON EST ICI
1. Structure du projet
2. Agent CV Optimizer : upload PDF → extraction texte → optimisation ATS → profil JSON
3. Scraping offres via SerpAPI (Google Jobs)
4. Scoring de pertinence (profil vs offre)

### Phase 2 — Génération & Dashboard (Semaines 7-10)
5. Agent Cover Letter Writer
6. Agent Quality Reviewer
7. Dashboard Streamlit pour l'utilisateur

### Phase 3 — Automatisation (Semaines 11+)
8. Agent Applicator (Playwright sur Indeed/HelloWork)
9. Agent Outreach (Gmail API + enrichissement contacts)
10. Séquences de relance

---

## Structure du projet (à créer)
```
job-apply-ai/
├── CLAUDE.md
├── README.md
├── .gitignore
├── .env                    # Clés API (jamais commité)
├── requirements.txt
├── agents/
│   ├── __init__.py
│   ├── cv_optimizer.py     # Agent 1 : analyse et optimise le CV
│   ├── scraper.py          # Agent 2 : scrape et score les offres
│   ├── cover_letter.py     # Agent 3 : génère les lettres de motivation
│   ├── quality_reviewer.py # Agent 4 : relit et valide
│   ├── applicator.py       # Agent 5 : postule automatiquement
│   └── outreach.py         # Agent 6 : emails recruteurs
├── core/
│   ├── __init__.py
│   ├── config.py           # Configuration, variables d'env
│   ├── models.py           # Modèles de données (profil, offre, candidature)
│   └── database.py         # Connexion BDD
├── utils/
│   ├── __init__.py
│   ├── pdf_parser.py       # Extraction texte PDF
│   └── llm_client.py       # Client API Claude/OpenAI
├── workflows/              # Configs n8n (export JSON)
├── dashboard/              # Frontend Streamlit
│   └── app.py
└── tests/
    └── test_cv_optimizer.py
```

---

## Commandes utiles
```bash
# Activer l'environnement virtuel
python3 -m venv .venv
source .venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Lancer le dashboard
streamlit run dashboard/app.py

# Git workflow
git add .
git commit -m "description claire"
git push
```

---

## Conventions de code
- **Langue du code** : anglais (noms de variables, fonctions, classes)
- **Langue des commentaires et docs** : français
- **Style** : PEP 8, docstrings en français
- **Commits** : messages en français, clairs et descriptifs
- **Secrets** : jamais dans le code, toujours dans .env
