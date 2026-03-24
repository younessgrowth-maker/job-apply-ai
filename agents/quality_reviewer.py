"""Agent Quality Reviewer — Relit et valide les lettres de motivation avant envoi.

Évalue chaque lettre selon plusieurs critères et propose des améliorations.
"""

from __future__ import annotations

import json
import logging

from utils.llm_client import ask_claude

logger = logging.getLogger(__name__)

# ── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_REVIEW = """\
Tu es un expert en recrutement et en rédaction professionnelle en France.
Tu relis des lettres de motivation et évalues leur qualité.
Réponds UNIQUEMENT en JSON valide, sans texte autour."""

PROMPT_REVIEW = """\
Relis cette lettre de motivation et évalue sa qualité.

## Contexte
- Candidat : {name}
- Poste visé : {job_title}
- Entreprise : {company}
- Type de contrat : {contract_type}

## Lettre de motivation
---
{letter}
---

Évalue selon ces critères (chacun sur 20 points, total sur 100) :
1. **Accroche** : La première phrase capte-t-elle l'attention ?
2. **Pertinence** : La lettre est-elle adaptée au poste et à l'entreprise ?
3. **Compétences** : Les compétences mises en avant correspondent-elles à l'offre ?
4. **Ton** : Le ton est-il professionnel, naturel et non générique ?
5. **Structure** : L'organisation est-elle claire (intro, corps, conclusion) ?

Retourne ce JSON exact :
{{
  "score": <entier 0-100>,
  "details": {{
    "accroche": <0-20>,
    "pertinence": <0-20>,
    "competences": <0-20>,
    "ton": <0-20>,
    "structure": <0-20>
  }},
  "points_forts": ["point fort 1", "point fort 2"],
  "suggestions": ["suggestion 1", "suggestion 2", "suggestion 3"],
  "verdict": "prête" | "à améliorer" | "à refaire"
}}"""


# ── Agent ────────────────────────────────────────────────────────────────────

def review_letter(
    letter: str,
    name: str,
    job_title: str,
    company: str,
    contract_type: str = "",
) -> dict:
    """Relit une lettre de motivation et retourne un scoring détaillé."""
    prompt = PROMPT_REVIEW.format(
        name=name,
        job_title=job_title,
        company=company,
        contract_type=contract_type,
        letter=letter,
    )
    response = ask_claude(prompt=prompt, system=SYSTEM_REVIEW)
    return _parse_json(response)


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
        logger.error("Échec parsing JSON review : %s\nRéponse :\n%s", e, text[:500])
        raise ValueError(f"Le LLM n'a pas retourné un JSON valide : {e}") from e
