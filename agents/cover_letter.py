"""Agent Cover Letter Writer — Génère une lettre de motivation unique par offre.

Pipeline :
  1. Charger le profil (profiles.json) et les offres scorées (jobs.json)
  2. Filtrer les offres avec score >= 70 (recommandation "postuler")
  3. Générer une lettre personnalisée pour chaque offre via LLM
  4. Relecture par l'Agent Quality Reviewer (scoring + suggestions)
  5. Sauvegarder dans output/cover_letters/
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from core.config import BASE_DIR
from core.models import UserProfile
from core.database import get_latest_profile
from utils.llm_client import ask_claude
from agents.quality_reviewer import review_letter

logger = logging.getLogger(__name__)

JOBS_FILE = BASE_DIR / "jobs.json"
OUTPUT_DIR = BASE_DIR / "output" / "cover_letters"

MIN_SCORE = 70  # Score minimum pour générer une lettre


# ── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_COVER_LETTER = """\
Tu es un expert en rédaction de lettres de motivation en français.
Tu rédiges des lettres percutantes, personnalisées et professionnelles.
Tu écris directement la lettre, sans commentaire ni explication autour."""

PROMPT_COVER_LETTER = """\
Rédige une lettre de motivation en français pour cette candidature.

## Candidat
- Nom : {name}
- Titre : {title}
- Formation : {education}
- Compétences clés : {skills}
- Expérience pertinente : {experience}
- Localisation : {location}
- Email : {email} | Tél : {phone}

## Offre ciblée
- Poste : {job_title}
- Entreprise : {company}
- Lieu : {job_location}
- Type de contrat : {contract_type}
- Description : {job_description}

## Points forts à valoriser (issus du scoring)
{scoring_reasons}

## Compétences manquantes à ne PAS mentionner
{missing_skills}

## Consignes de rédaction
1. Commence par une accroche originale liée à l'entreprise ou au secteur (pas "Je me permets de...")
2. Montre que tu connais l'entreprise et son secteur
3. Mets en avant 2-3 expériences/compétences directement liées au poste
4. Inclus des résultats chiffrés quand c'est possible
5. Termine par une phrase d'ouverture vers un entretien
6. Ton : professionnel mais naturel, pas trop formel
7. Longueur : 250-350 mots maximum
8. N'invente AUCUNE information — utilise uniquement les données du profil
9. Adapte le vocabulaire au secteur de l'entreprise

Écris directement la lettre, sans titre ni commentaire."""


# ── Chargement des données ───────────────────────────────────────────────────

def load_jobs(min_score: float = MIN_SCORE) -> list[dict]:
    """Charge les offres depuis jobs.json et filtre par score minimum."""
    if not JOBS_FILE.exists():
        raise FileNotFoundError(
            "jobs.json introuvable. Lancez d'abord l'agent scraper : "
            "python -m agents.scraper"
        )
    data = json.loads(JOBS_FILE.read_text())
    offers = data.get("offers", [])
    filtered = [o for o in offers if o.get("match_score", 0) >= min_score]
    logger.info(
        "%d offres chargées, %d avec score >= %d",
        len(offers), len(filtered), min_score,
    )
    return filtered


# ── Génération ───────────────────────────────────────────────────────────────

def generate_cover_letter(profile: UserProfile, offer: dict) -> str:
    """Génère une lettre de motivation personnalisée pour une offre."""
    # Préparer les expériences pertinentes (les 2 plus récentes)
    exp_text = ""
    for exp in profile.experiences[:2]:
        exp_text += f"- {exp.title} chez {exp.company} ({exp.start_date} – {exp.end_date}) : {exp.description[:200]}\n"

    # Préparer la formation
    edu_text = ", ".join(
        f"{e.degree} ({e.institution})" for e in profile.education[:2]
    )

    # Scoring du scraper
    scoring = offer.get("scoring", {})
    reasons = scoring.get("reasons", [])
    missing = scoring.get("missing_skills", [])
    reasons_text = "\n".join(f"- {r}" for r in reasons[:3]) if reasons else "- Bonne correspondance générale"
    missing_text = ", ".join(missing[:3]) if missing else "Aucune"

    prompt = PROMPT_COVER_LETTER.format(
        name=profile.full_name,
        title=profile.title,
        education=edu_text,
        skills=", ".join(profile.skills[:12]),
        experience=exp_text,
        location=profile.location,
        email=profile.email,
        phone=profile.phone,
        job_title=offer["title"],
        company=offer["company"],
        job_location=offer["location"],
        contract_type=offer["contract_type"],
        job_description=offer["description"][:600],
        scoring_reasons=reasons_text,
        missing_skills=missing_text,
    )

    return ask_claude(prompt=prompt, system=SYSTEM_COVER_LETTER)


def _sanitize_filename(text: str) -> str:
    """Convertit un texte en nom de fichier sûr."""
    text = text.lower().strip()
    text = re.sub(r"[àáâãäå]", "a", text)
    text = re.sub(r"[èéêë]", "e", text)
    text = re.sub(r"[ìíîï]", "i", text)
    text = re.sub(r"[òóôõö]", "o", text)
    text = re.sub(r"[ùúûü]", "u", text)
    text = re.sub(r"[ç]", "c", text)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    return text[:50]


def save_cover_letter(
    letter: str,
    company: str,
    job_title: str,
    review: dict | None = None,
) -> Path:
    """Sauvegarde la lettre en markdown dans output/cover_letters/."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    company_clean = _sanitize_filename(company)
    title_clean = _sanitize_filename(job_title)
    filename = f"lettre_{company_clean}_{title_clean}.md"
    filepath = OUTPUT_DIR / filename

    # Construire le contenu markdown
    content = f"# Lettre de motivation — {job_title} @ {company}\n\n"
    content += f"*Générée le {datetime.now().strftime('%d/%m/%Y à %H:%M')}*\n\n"
    content += "---\n\n"
    content += letter
    content += "\n\n---\n\n"

    # Ajouter la revue qualité si disponible
    if review:
        score = review.get("score", 0)
        verdict = review.get("verdict", "?")
        details = review.get("details", {})
        points_forts = review.get("points_forts", [])
        suggestions = review.get("suggestions", [])

        content += f"## Revue qualité — {score}/100 ({verdict})\n\n"
        content += "| Critère | Score |\n|---------|-------|\n"
        for critere, val in details.items():
            content += f"| {critere.capitalize()} | {val}/20 |\n"

        if points_forts:
            content += f"\n**Points forts** : {'; '.join(points_forts)}\n"
        if suggestions:
            content += "\n**Suggestions** :\n"
            for s in suggestions:
                content += f"- {s}\n"

    filepath.write_text(content, encoding="utf-8")
    return filepath


# ── Pipeline principal ───────────────────────────────────────────────────────

def run_cover_letters(
    profile: UserProfile | None = None,
    min_score: float = MIN_SCORE,
    skip_review: bool = False,
) -> list[dict]:
    """Pipeline complet : chargement → génération → revue → sauvegarde.

    Args:
        profile: Profil utilisateur (si None, charge le dernier).
        min_score: Score minimum pour générer une lettre.
        skip_review: Si True, ne pas faire la revue qualité.

    Returns:
        Liste de dicts {offer, letter, review, filepath}.
    """
    # Charger le profil
    if profile is None:
        profile = get_latest_profile()
        if profile is None:
            raise RuntimeError(
                "Aucun profil trouvé. Lancez d'abord : python -m agents.cv_optimizer"
            )
    logger.info("Profil : %s", profile.full_name)

    # Charger les offres filtrées
    offers = load_jobs(min_score=min_score)
    if not offers:
        logger.warning("Aucune offre avec score >= %d. Rien à générer.", min_score)
        return []

    results = []

    for i, offer in enumerate(offers, 1):
        company = offer["company"]
        job_title = offer["title"]
        score = offer["match_score"]

        logger.info(
            "Lettre %d/%d : %s @ %s (score: %.0f/100)",
            i, len(offers), job_title, company, score,
        )

        # Génération
        logger.info("  Génération de la lettre...")
        letter = generate_cover_letter(profile, offer)

        # Revue qualité
        review = None
        if not skip_review:
            logger.info("  Revue qualité en cours...")
            try:
                review = review_letter(
                    letter=letter,
                    name=profile.full_name,
                    job_title=job_title,
                    company=company,
                    contract_type=offer.get("contract_type", ""),
                )
                verdict = review.get("verdict", "?")
                review_score = review.get("score", 0)
                logger.info("  → Qualité : %d/100 — %s", review_score, verdict)
            except Exception as e:
                logger.warning("  → Erreur revue qualité : %s", e)

        # Sauvegarde
        filepath = save_cover_letter(letter, company, job_title, review)
        logger.info("  → Sauvegardée : %s", filepath.name)

        results.append({
            "offer": offer,
            "letter": letter,
            "review": review,
            "filepath": str(filepath),
        })

    return results


# ── Point d'entrée CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    skip_review = "--no-review" in sys.argv

    results = run_cover_letters(skip_review=skip_review)

    if not results:
        print("\nAucune lettre générée (pas d'offre avec score >= 70).")
        sys.exit(0)

    # Affichage récapitulatif
    print("\n" + "=" * 70)
    print(f"  {len(results)} LETTRES DE MOTIVATION GÉNÉRÉES")
    print("=" * 70)

    for i, r in enumerate(results, 1):
        offer = r["offer"]
        review = r["review"]
        filepath = r["filepath"]

        review_info = ""
        if review:
            review_info = f" | Qualité : {review.get('score', '?')}/100 ({review.get('verdict', '?')})"

        print(f"\n  #{i} — {offer['title']} @ {offer['company']}")
        print(f"       Match : {offer['match_score']:.0f}/100{review_info}")
        print(f"       Fichier : {Path(filepath).name}")

        if review and review.get("suggestions"):
            print(f"       Suggestions : {'; '.join(review['suggestions'][:2])}")

    print("\n" + "=" * 70)
    print(f"  Lettres sauvegardées dans output/cover_letters/")
    print("=" * 70)
