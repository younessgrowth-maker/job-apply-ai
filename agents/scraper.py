"""Agent Scraper/Matcher — Recherche d'offres d'emploi et scoring par pertinence.

Pipeline :
  1. Charger le profil structuré depuis profiles.json
  2. Construire les requêtes de recherche (titre + localisation)
  3. Chercher via SerpAPI (Google Jobs) ou mode démo (offres fictives)
  4. Scorer chaque offre par pertinence via LLM (0-100)
  5. Sauvegarder les résultats triés dans jobs.json
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from core.config import BASE_DIR, SERPAPI_API_KEY
from core.models import UserProfile, JobOffer
from core.database import get_latest_profile
from utils.llm_client import ask_claude

logger = logging.getLogger(__name__)

JOBS_FILE = BASE_DIR / "jobs.json"


# ── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_SCORE = """\
Tu es un expert en recrutement tech et data en France.
Tu évalues la pertinence d'une offre d'emploi par rapport au profil d'un candidat.
Réponds UNIQUEMENT en JSON valide, sans texte autour."""

PROMPT_SCORE = """\
Évalue la pertinence de cette offre par rapport au profil du candidat.

## Profil du candidat
- Nom : {name}
- Titre : {title}
- Compétences : {skills}
- Mots-clés ATS : {keywords}
- Localisation : {location}
- Recherche : alternance Data/IA

## Offre d'emploi
- Poste : {job_title}
- Entreprise : {job_company}
- Lieu : {job_location}
- Type de contrat : {job_contract}
- Description : {job_description}

Analyse et retourne ce JSON exact :
{{
  "score": <entier de 0 à 100>,
  "reasons": ["raison1", "raison2", "raison3"],
  "missing_skills": ["compétence manquante 1", ...],
  "recommendation": "postuler" | "peut-être" | "passer"
}}

Critères de scoring :
- Correspondance titre/poste (30 points)
- Correspondance compétences techniques (30 points)
- Localisation / télétravail compatible (15 points)
- Type de contrat adapté (alternance, stage, CDI junior) (15 points)
- Secteur / culture d'entreprise (10 points)"""


# ── Sources d'offres ─────────────────────────────────────────────────────────

def search_serpapi(query: str, location: str, num_results: int = 10) -> list[dict]:
    """Recherche d'offres via SerpAPI (Google Jobs).

    Nécessite SERPAPI_API_KEY dans le .env.
    """
    try:
        from serpapi import GoogleSearch
    except ImportError:
        raise ImportError("Installez google-search-results : pip install google-search-results")

    params = {
        "engine": "google_jobs",
        "q": query,
        "location": location,
        "hl": "fr",
        "api_key": SERPAPI_API_KEY,
        "num": num_results,
    }
    search = GoogleSearch(params)
    results = search.get_dict()
    jobs_results = results.get("jobs_results", [])

    offers = []
    for job in jobs_results:
        offers.append({
            "title": job.get("title", ""),
            "company": job.get("company_name", ""),
            "location": job.get("location", ""),
            "description": job.get("description", "")[:1500],
            "url": job.get("share_link", job.get("related_links", [{}])[0].get("link", "")),
            "source": "google_jobs",
            "contract_type": _extract_contract_type(job),
            "salary": job.get("detected_extensions", {}).get("salary", ""),
        })

    return offers


def _extract_contract_type(job: dict) -> str:
    """Extrait le type de contrat depuis les extensions Google Jobs."""
    extensions = job.get("detected_extensions", {})
    schedule = extensions.get("schedule_type", "")
    highlights = job.get("job_highlights", [])
    qualifications = " ".join(highlights[0].get("items", [])[:3]) if highlights else ""
    text = f"{schedule} {qualifications}".lower()
    if "alternance" in text or "apprentissage" in text:
        return "alternance"
    if "stage" in text or "intern" in text:
        return "stage"
    if "cdi" in text:
        return "CDI"
    if "cdd" in text:
        return "CDD"
    if "freelance" in text:
        return "freelance"
    return schedule or "non précisé"


def search_demo(query: str, location: str) -> list[dict]:
    """Retourne des offres fictives pour tester le pipeline sans clé SerpAPI."""
    logger.info("Mode DEMO — offres fictives générées pour '%s' à '%s'", query, location)
    return [
        {
            "title": "Data Analyst en alternance",
            "company": "BNP Paribas",
            "location": "Paris, France",
            "description": (
                "Rejoignez notre équipe Data Analytics en alternance. "
                "Missions : analyse de données clients avec Python et SQL, "
                "création de dashboards Power BI, mise en place de pipelines ETL. "
                "Profil recherché : étudiant en école d'ingénieur spécialisation Data/IA, "
                "maîtrise de Python (Pandas, NumPy), SQL, et outils de BI. "
                "Rythme : 3 semaines entreprise / 1 semaine école."
            ),
            "url": "https://emploi.bnpparibas.com/offre/data-analyst-alternance",
            "source": "demo",
            "contract_type": "alternance",
            "salary": "",
        },
        {
            "title": "Alternant Data Engineer",
            "company": "Société Générale",
            "location": "La Défense, France",
            "description": (
                "Au sein de la direction Data, vous contribuerez à la construction "
                "de pipelines de données (Python, Spark, SQL). "
                "Vous participerez au développement de modèles ML pour la détection de fraude. "
                "Stack : Python, PySpark, AWS, Airflow, PostgreSQL, Docker. "
                "Recherche alternant en Data Engineering pour 2 ans, dès septembre 2025."
            ),
            "url": "https://careers.societegenerale.com/data-engineer-alternance",
            "source": "demo",
            "contract_type": "alternance",
            "salary": "",
        },
        {
            "title": "Stage Data Scientist – NLP",
            "company": "Dataiku",
            "location": "Paris 2e, France",
            "description": (
                "Stage de 6 mois en Data Science appliquée au NLP. "
                "Vous travaillerez sur des modèles de classification de texte "
                "et d'extraction d'information (transformers, BERT). "
                "Compétences requises : Python, scikit-learn, PyTorch ou TensorFlow, SQL. "
                "Startup à forte croissance, environnement international."
            ),
            "url": "https://www.dataiku.com/careers/stage-data-scientist-nlp",
            "source": "demo",
            "contract_type": "stage",
            "salary": "1200€/mois",
        },
        {
            "title": "Développeur Full Stack React/Node.js",
            "company": "Capgemini",
            "location": "Issy-les-Moulineaux, France",
            "description": (
                "CDI développeur Full Stack pour projets web grands comptes. "
                "Stack : React, Node.js, TypeScript, MongoDB, AWS. "
                "3+ ans d'expérience requis. Méthodologie Agile/Scrum."
            ),
            "url": "https://www.capgemini.com/careers/fullstack-dev",
            "source": "demo",
            "contract_type": "CDI",
            "salary": "42-48K€",
        },
        {
            "title": "Alternant Machine Learning Engineer",
            "company": "Orange",
            "location": "Châtillon, France",
            "description": (
                "Intégrez l'équipe IA d'Orange pour développer des modèles de ML "
                "appliqués aux réseaux télécoms. Missions : feature engineering, "
                "entraînement de modèles (scikit-learn, XGBoost), déploiement MLOps. "
                "Profil : M1/M2 ou ingénieur en Data Science/IA, Python, SQL. "
                "Alternance 2 ans, rythme flexible."
            ),
            "url": "https://orange.jobs/ml-engineer-alternance",
            "source": "demo",
            "contract_type": "alternance",
            "salary": "",
        },
        {
            "title": "Consultant BI Junior – Power BI / Tableau",
            "company": "Accenture",
            "location": "Paris, France",
            "description": (
                "Missions de consulting en Business Intelligence pour des clients CAC 40. "
                "Création de dashboards, analyse de données, formation utilisateurs. "
                "Outils : Power BI, Tableau, SQL, Excel avancé. "
                "Profil : Bac+5, première expérience en BI appréciée."
            ),
            "url": "https://www.accenture.com/careers/consultant-bi-junior",
            "source": "demo",
            "contract_type": "CDI",
            "salary": "35-40K€",
        },
        {
            "title": "Chef de projet marketing digital",
            "company": "L'Oréal",
            "location": "Clichy, France",
            "description": (
                "Pilotage de campagnes digitales pour marques grand public. "
                "Gestion de budgets media, coordination agences, analyse ROI. "
                "5 ans d'expérience minimum en marketing digital. "
                "Compétences : Google Ads, Meta Ads, CRM Salesforce."
            ),
            "url": "https://careers.loreal.com/chef-projet-marketing",
            "source": "demo",
            "contract_type": "CDI",
            "salary": "50-60K€",
        },
        {
            "title": "Data Analyst – Alternance 2 ans",
            "company": "EDF",
            "location": "Saint-Denis, France",
            "description": (
                "Alternance au sein de la direction Data d'EDF. "
                "Analyse de données de consommation énergétique, "
                "création de tableaux de bord en Python (Streamlit) et Power BI, "
                "requêtes SQL sur PostgreSQL, automatisation de rapports. "
                "Profil recherché : école d'ingénieur ou master Data/IA, "
                "Python, SQL, notions de Machine Learning."
            ),
            "url": "https://www.edf.fr/recrutement/data-analyst-alternance",
            "source": "demo",
            "contract_type": "alternance",
            "salary": "",
        },
    ]


# ── Scoring ──────────────────────────────────────────────────────────────────

def score_offer(profile: UserProfile, offer: dict) -> dict:
    """Score une offre par rapport au profil via LLM. Retourne le scoring JSON."""
    prompt = PROMPT_SCORE.format(
        name=profile.full_name,
        title=profile.title,
        skills=", ".join(profile.skills[:15]),
        keywords=", ".join(profile.keywords_ats[:10]),
        location=profile.location,
        job_title=offer["title"],
        job_company=offer["company"],
        job_location=offer["location"],
        job_contract=offer["contract_type"],
        job_description=offer["description"][:800],
    )
    response = ask_claude(prompt=prompt, system=SYSTEM_SCORE)
    return _parse_json(response)


def score_all_offers(profile: UserProfile, offers: list[dict]) -> list[dict]:
    """Score toutes les offres et retourne des JobOffer triées par score décroissant."""
    scored_jobs = []

    for i, offer in enumerate(offers, 1):
        logger.info("Scoring offre %d/%d : %s @ %s", i, len(offers), offer["title"], offer["company"])
        try:
            scoring = score_offer(profile, offer)
            score = scoring.get("score", 0)
            reasons = scoring.get("reasons", [])
            recommendation = scoring.get("recommendation", "")
            missing = scoring.get("missing_skills", [])

            job = JobOffer(
                title=offer["title"],
                company=offer["company"],
                location=offer["location"],
                description=offer["description"],
                url=offer["url"],
                source=offer["source"],
                contract_type=offer["contract_type"],
                salary=offer.get("salary", ""),
                match_score=score,
            )
            scored_jobs.append({
                "job": job,
                "reasons": reasons,
                "recommendation": recommendation,
                "missing_skills": missing,
            })
            logger.info("  → Score : %d/100 — %s", score, recommendation)

        except Exception as e:
            logger.warning("  → Erreur de scoring pour '%s' : %s", offer["title"], e)
            job = JobOffer(
                title=offer.get("title", ""),
                company=offer.get("company", ""),
                location=offer.get("location", ""),
                description=offer.get("description", ""),
                url=offer.get("url", ""),
                source=offer.get("source", ""),
                contract_type=offer.get("contract_type", ""),
                salary=offer.get("salary", ""),
            )
            scored_jobs.append({
                "job": job,
                "reasons": [],
                "recommendation": "erreur",
                "missing_skills": [],
            })

    # Trier par score décroissant
    scored_jobs.sort(key=lambda x: x["job"].match_score, reverse=True)
    return scored_jobs


# ── Sauvegarde ───────────────────────────────────────────────────────────────

def save_jobs(scored_jobs: list[dict], profile_name: str) -> Path:
    """Sauvegarde les offres scorées dans jobs.json."""
    output = {
        "profile": profile_name,
        "search_date": datetime.now().isoformat(),
        "total_offers": len(scored_jobs),
        "offers": [],
    }
    for item in scored_jobs:
        job = item["job"]
        output["offers"].append({
            **job.model_dump(mode="json"),
            "scoring": {
                "score": job.match_score,
                "reasons": item["reasons"],
                "recommendation": item["recommendation"],
                "missing_skills": item["missing_skills"],
            },
        })

    JOBS_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    logger.info("Résultats sauvegardés dans %s", JOBS_FILE)
    return JOBS_FILE


# ── Pipeline principal ───────────────────────────────────────────────────────

def run_scraper(profile: UserProfile | None = None, use_demo: bool = False) -> list[dict]:
    """Pipeline complet : chargement profil → recherche → scoring → sauvegarde.

    Args:
        profile: Profil utilisateur (si None, charge le dernier depuis profiles.json).
        use_demo: Si True, utilise des offres fictives au lieu de SerpAPI.

    Returns:
        Liste des offres scorées.
    """
    # Charger le profil
    if profile is None:
        profile = get_latest_profile()
        if profile is None:
            raise RuntimeError(
                "Aucun profil trouvé dans profiles.json. "
                "Lancez d'abord l'agent CV Optimizer."
            )
    logger.info("Profil chargé : %s — %s", profile.full_name, profile.title)

    # Construire la requête de recherche
    search_title = profile.title.split("–")[0].strip() if "–" in profile.title else profile.title
    search_location = profile.location.split(",")[0].strip() if "," in profile.location else profile.location
    query = f"{search_title} alternance"
    logger.info("Requête de recherche : '%s' à '%s'", query, search_location)

    # Décider de la source
    if use_demo or not SERPAPI_API_KEY or SERPAPI_API_KEY == "xxx":
        offers = search_demo(query, search_location)
    else:
        logger.info("Recherche via SerpAPI (Google Jobs)...")
        offers = search_serpapi(query, search_location)
        if not offers:
            logger.warning("Aucune offre trouvée via SerpAPI, basculement en mode démo.")
            offers = search_demo(query, search_location)

    logger.info("%d offres trouvées", len(offers))

    # Scorer via LLM
    logger.info("Scoring des offres via LLM...")
    scored_jobs = score_all_offers(profile, offers)

    # Sauvegarder
    save_jobs(scored_jobs, profile.full_name)

    return scored_jobs


# ── Utilitaires ──────────────────────────────────────────────────────────────

def _parse_json(text: str) -> dict:
    """Extrait et parse le JSON depuis une réponse LLM."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("Échec parsing JSON : %s\nRéponse :\n%s", e, text[:500])
        raise ValueError(f"Le LLM n'a pas retourné un JSON valide : {e}") from e


# ── Point d'entrée CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    # Argument optionnel : --live pour utiliser SerpAPI au lieu du mode démo
    use_demo = "--live" not in sys.argv

    if use_demo:
        logger.info("Mode DEMO (offres fictives). Ajoutez --live pour utiliser SerpAPI.")

    scored_jobs = run_scraper(use_demo=use_demo)

    # Affichage des résultats
    print("\n" + "=" * 70)
    print(f"  RÉSULTATS — {len(scored_jobs)} offres scorées")
    print("=" * 70)

    for i, item in enumerate(scored_jobs, 1):
        job = item["job"]
        rec = item["recommendation"]
        reasons = item["reasons"]
        missing = item["missing_skills"]

        icon = {"postuler": "[+++]", "peut-être": "[ + ]", "passer": "[ - ]", "erreur": "[ERR]"}.get(rec, "[ ? ]")

        print(f"\n{icon} #{i} — {job.match_score:.0f}/100 — {job.title}")
        print(f"      Entreprise : {job.company}")
        print(f"      Lieu : {job.location} | Contrat : {job.contract_type}")
        if reasons:
            print(f"      Raisons : {'; '.join(reasons[:3])}")
        if missing:
            print(f"      Manque : {', '.join(missing[:3])}")

    print("\n" + "=" * 70)
    print(f"  Résultats sauvegardés dans jobs.json")
    print("=" * 70)
