"""Agent CV Optimizer — Analyse, extrait et optimise un CV pour les systèmes ATS.

Pipeline :
  1. Extraction du texte brut (PDF / DOCX)
  2. Structuration via LLM → UserProfile JSON
  3. Optimisation ATS (mots-clés, reformulation)
  4. Sauvegarde du profil en base
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from core.models import UserProfile
from core.database import save_profile
from utils.pdf_parser import extract_text
from utils.llm_client import ask_claude

logger = logging.getLogger(__name__)

# ── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_EXTRACT = """\
Tu es un expert en recrutement et en systèmes ATS (Applicant Tracking Systems).
Tu analyses des CV et en extrais les informations structurées.
Réponds UNIQUEMENT en JSON valide, sans texte autour."""

PROMPT_EXTRACT = """\
Analyse le CV ci-dessous et extrais les informations dans ce format JSON exact :

{{
  "full_name": "...",
  "email": "...",
  "phone": "...",
  "location": "...",
  "title": "Titre professionnel le plus pertinent",
  "summary": "Résumé professionnel en 2-3 phrases",
  "skills": ["compétence1", "compétence2", ...],
  "experiences": [
    {{
      "title": "...",
      "company": "...",
      "start_date": "...",
      "end_date": "...",
      "description": "Missions principales en bullet points"
    }}
  ],
  "education": [
    {{
      "degree": "...",
      "institution": "...",
      "year": "..."
    }}
  ],
  "languages": ["Français (natif)", "Anglais (B2)", ...]
}}

CV à analyser :
---
{cv_text}
---"""

SYSTEM_OPTIMIZE = """\
Tu es un expert en optimisation de CV pour les systèmes ATS.
Tu reformules et enrichis les profils professionnels pour maximiser le score ATS
tout en restant fidèle au parcours réel du candidat."""

PROMPT_OPTIMIZE = """\
Voici le profil structuré d'un candidat (JSON) :

{profile_json}

Optimise ce profil pour les systèmes ATS :

1. **summary** : Réécris le résumé en incluant des mots-clés sectoriels pertinents.
2. **skills** : Complète avec des compétences connexes manquantes (outils, frameworks, méthodes).
3. **experiences** : Reformule les descriptions avec des verbes d'action mesurables
   (ex: "Développé", "Optimisé", "Réduit de X%"). Garde les faits réels.
4. **keywords_ats** : Génère une liste de 10-20 mots-clés ATS pertinents pour ce profil.

Réponds UNIQUEMENT en JSON valide avec la même structure, enrichie.
Garde tous les champs existants, ne supprime rien."""


# ── Agent ────────────────────────────────────────────────────────────────────

def optimize_cv(file_path: str | Path) -> UserProfile:
    """Pipeline complet : extraction → structuration → optimisation ATS.

    Args:
        file_path: Chemin vers le CV (PDF ou DOCX).

    Returns:
        UserProfile optimisé et sauvegardé en base.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    # Étape 1 — Extraction du texte brut
    logger.info("Extraction du texte depuis %s", path.name)
    raw_text = extract_text(path)
    if not raw_text.strip():
        raise ValueError("Aucun texte extrait du fichier. Vérifiez que le PDF n'est pas scanné.")

    logger.info("Texte extrait : %d caractères", len(raw_text))

    # Étape 2 — Structuration via LLM
    logger.info("Structuration du CV via LLM...")
    extract_response = ask_claude(
        prompt=PROMPT_EXTRACT.format(cv_text=raw_text),
        system=SYSTEM_EXTRACT,
    )
    profile_data = _parse_json(extract_response)
    profile_data["raw_text"] = raw_text

    # Étape 3 — Optimisation ATS via LLM
    logger.info("Optimisation ATS via LLM...")
    optimize_response = ask_claude(
        prompt=PROMPT_OPTIMIZE.format(profile_json=json.dumps(profile_data, ensure_ascii=False)),
        system=SYSTEM_OPTIMIZE,
    )
    optimized_data = _parse_json(optimize_response)

    # Fusionner : garder raw_text et champs d'origine non modifiés
    optimized_data["raw_text"] = raw_text
    profile = UserProfile(**optimized_data)

    # Étape 4 — Sauvegarde
    save_profile(profile)
    logger.info("Profil optimisé sauvegardé pour %s", profile.full_name)

    return profile


def _parse_json(text: str) -> dict:
    """Extrait et parse le JSON depuis une réponse LLM (gère les blocs ```json)."""
    cleaned = text.strip()
    # Retirer les blocs de code markdown
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Enlever la première et dernière ligne (```json et ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("Échec du parsing JSON : %s\nRéponse LLM :\n%s", e, text[:500])
        raise ValueError(
            f"Le LLM n'a pas retourné un JSON valide. Erreur : {e}"
        ) from e


# ── Point d'entrée CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    if len(sys.argv) < 2:
        print("Usage : python -m agents.cv_optimizer <chemin_cv.pdf>")
        sys.exit(1)

    result = optimize_cv(sys.argv[1])
    print("\n" + "=" * 60)
    print(f"Profil optimisé pour : {result.full_name}")
    print(f"Titre : {result.title}")
    print(f"Compétences : {', '.join(result.skills[:10])}")
    print(f"Mots-clés ATS : {', '.join(result.keywords_ats[:10])}")
    print(f"Expériences : {len(result.experiences)}")
    print("=" * 60)
    print("\nJSON complet :")
    print(result.model_dump_json(indent=2))
