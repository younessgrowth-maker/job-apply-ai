"""Agent Applicator — Envoie les candidatures par email.

Pipeline :
  1. Charger les offres éligibles (score >= 70) depuis jobs.json
  2. Retrouver la lettre de motivation correspondante dans output/cover_letters/
  3. Générer un email personnalisé (objet + corps) via LLM
  4. Envoyer par SMTP (Gmail) avec CV en pièce jointe, ou simuler l'envoi
  5. Mettre à jour le statut dans jobs.json
  6. Générer un rapport de suivi dans output/applications_report.md

Modes :
  - simulation (défaut) : log tout sans rien envoyer
  - email (--send) : envoi réel via SMTP
"""

from __future__ import annotations

import json
import logging
import re
import smtplib
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from core.config import (
    BASE_DIR, SMTP_EMAIL, SMTP_PASSWORD, SMTP_HOST, SMTP_PORT,
)
from core.database import get_latest_profile
from core.models import UserProfile
from utils.llm_client import ask_claude

logger = logging.getLogger(__name__)

JOBS_FILE = BASE_DIR / "jobs.json"
COVER_LETTERS_DIR = BASE_DIR / "output" / "cover_letters"
OUTPUT_DIR = BASE_DIR / "output"
UPLOADS_DIR = BASE_DIR / "uploads"

MIN_MATCH_SCORE = 70
MIN_QUALITY_SCORE = 80


# ── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_EMAIL = """\
Tu es un expert en rédaction d'emails de candidature professionnels en français.
Tu rédiges des emails concis, professionnels et personnalisés.
Réponds UNIQUEMENT en JSON valide, sans texte autour."""

PROMPT_EMAIL = """\
Rédige un email de candidature pour ce poste.

## Candidat
- Nom : {name}
- Titre : {title}
- Email : {email}
- Tél : {phone}

## Offre
- Poste : {job_title}
- Entreprise : {company}
- Lieu : {job_location}
- Contrat : {contract_type}

## Contexte
La lettre de motivation est jointe en pièce jointe avec le CV.
L'email doit donner envie d'ouvrir les pièces jointes.

Retourne ce JSON exact :
{{
  "subject": "Objet de l'email (court, percutant, avec le nom du poste)",
  "body": "Corps de l'email en texte brut. 4-6 phrases maximum. Mentionner que le CV et la lettre de motivation sont en pièce jointe. Terminer par une formule de politesse courte."
}}

Consignes :
- Objet : inclure le nom du poste et le type de contrat
- Corps : bref, direct, professionnel mais pas froid
- Ne PAS recopier la lettre de motivation dans l'email
- Mentionner 1 point fort clé du candidat pour accrocher
- Pas de "Je me permets de..." ni de formules génériques"""


# ── Utilitaires ──────────────────────────────────────────────────────────────

def _sanitize_filename(text: str) -> str:
    """Convertit un texte en nom de fichier sûr (même logique que cover_letter.py)."""
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


def find_cover_letter(company: str, job_title: str) -> Path | None:
    """Retrouve le fichier de lettre de motivation correspondant."""
    company_clean = _sanitize_filename(company)
    title_clean = _sanitize_filename(job_title)
    expected = COVER_LETTERS_DIR / f"lettre_{company_clean}_{title_clean}.md"
    if expected.exists():
        return expected
    # Recherche approximative si le nom exact ne matche pas
    for f in COVER_LETTERS_DIR.glob(f"lettre_{company_clean}_*.md"):
        return f
    return None


def find_cv() -> Path | None:
    """Retrouve le CV le plus récent dans uploads/."""
    pdfs = sorted(UPLOADS_DIR.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    return pdfs[0] if pdfs else None


def extract_letter_text(letter_path: Path) -> str:
    """Extrait le texte de la lettre (sans les métadonnées markdown)."""
    content = letter_path.read_text(encoding="utf-8")
    # Extraire entre le premier et le deuxième "---"
    parts = content.split("---")
    if len(parts) >= 3:
        return parts[2].strip()
    return content


def get_quality_score(letter_path: Path) -> float | None:
    """Extrait le score qualité depuis le fichier de lettre (s'il existe)."""
    content = letter_path.read_text(encoding="utf-8")
    match = re.search(r"## Revue qualité — (\d+)/100", content)
    if match:
        return float(match.group(1))
    return None


# ── Chargement et filtrage ───────────────────────────────────────────────────

def load_eligible_offers() -> list[dict]:
    """Charge les offres éligibles à l'envoi (score >= 70 + lettre avec qualité >= 80)."""
    if not JOBS_FILE.exists():
        raise FileNotFoundError("jobs.json introuvable. Lancez d'abord le scraper.")

    data = json.loads(JOBS_FILE.read_text())
    offers = data.get("offers", [])
    eligible = []

    for offer in offers:
        match_score = offer.get("match_score", 0)
        if match_score < MIN_MATCH_SCORE:
            continue

        # Vérifier qu'une lettre existe et a un bon score qualité
        letter_path = find_cover_letter(offer["company"], offer["title"])
        if not letter_path:
            logger.info(
                "  Pas de lettre pour %s @ %s — ignorée",
                offer["title"], offer["company"],
            )
            continue

        quality = get_quality_score(letter_path)
        if quality is not None and quality < MIN_QUALITY_SCORE:
            logger.info(
                "  Lettre %s : qualité %.0f/100 < %d — ignorée",
                letter_path.name, quality, MIN_QUALITY_SCORE,
            )
            continue

        # Vérifier si déjà envoyée
        status = offer.get("application_status", "")
        if status == "envoyée":
            logger.info("  %s @ %s — déjà envoyée, ignorée", offer["title"], offer["company"])
            continue

        offer["_letter_path"] = str(letter_path)
        offer["_quality_score"] = quality
        eligible.append(offer)

    return eligible


# ── Génération email ─────────────────────────────────────────────────────────

def generate_email(profile: UserProfile, offer: dict) -> dict:
    """Génère l'objet et le corps de l'email via LLM."""
    prompt = PROMPT_EMAIL.format(
        name=profile.full_name,
        title=profile.title,
        email=profile.email,
        phone=profile.phone,
        job_title=offer["title"],
        company=offer["company"],
        job_location=offer["location"],
        contract_type=offer["contract_type"],
    )
    response = ask_claude(prompt=prompt, system=SYSTEM_EMAIL)
    return _parse_json(response)


# ── Envoi email ──────────────────────────────────────────────────────────────

def send_email(
    to_email: str,
    subject: str,
    body: str,
    cv_path: Path | None = None,
    letter_path: Path | None = None,
) -> bool:
    """Envoie un email via SMTP avec pièces jointes."""
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        raise RuntimeError(
            "SMTP_EMAIL et SMTP_PASSWORD requis dans .env. "
            "Utilisez un mot de passe d'application Gmail : "
            "https://myaccount.google.com/apppasswords"
        )

    msg = MIMEMultipart()
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject

    # Corps du mail
    msg.attach(MIMEText(body, "plain", "utf-8"))

    # CV en pièce jointe
    if cv_path and cv_path.exists():
        with open(cv_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=cv_path.name)
        part["Content-Disposition"] = f'attachment; filename="{cv_path.name}"'
        msg.attach(part)

    # Lettre de motivation en pièce jointe
    if letter_path and letter_path.exists():
        letter_text = extract_letter_text(letter_path)
        part = MIMEText(letter_text, "plain", "utf-8")
        part.add_header(
            "Content-Disposition", "attachment",
            filename="Lettre_de_motivation.txt",
        )
        msg.attach(part)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.send_message(msg)

    return True


# ── Mise à jour du statut ────────────────────────────────────────────────────

def update_job_status(company: str, title: str, status: str) -> None:
    """Met à jour le statut d'une offre dans jobs.json."""
    data = json.loads(JOBS_FILE.read_text())
    for offer in data.get("offers", []):
        if offer["company"] == company and offer["title"] == title:
            offer["application_status"] = status
            offer["application_date"] = datetime.now().isoformat()
            break
    JOBS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))


# ── Rapport ──────────────────────────────────────────────────────────────────

def generate_report(results: list[dict], mode: str) -> Path:
    """Génère un rapport markdown des candidatures."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / "applications_report.md"

    content = f"# Rapport de candidatures\n\n"
    content += f"*Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}*\n"
    content += f"*Mode : {mode}*\n\n"

    # Statistiques
    sent = sum(1 for r in results if r["status"] == "envoyée")
    simulated = sum(1 for r in results if r["status"] == "simulée")
    failed = sum(1 for r in results if r["status"] == "erreur")

    content += "## Résumé\n\n"
    content += f"| Métrique | Valeur |\n|----------|--------|\n"
    content += f"| Total | {len(results)} |\n"
    if simulated:
        content += f"| Simulées | {simulated} |\n"
    if sent:
        content += f"| Envoyées | {sent} |\n"
    if failed:
        content += f"| Erreurs | {failed} |\n"

    content += "\n## Détail\n\n"

    for i, r in enumerate(results, 1):
        offer = r["offer"]
        status_icon = {"envoyée": "[OK]", "simulée": "[SIM]", "erreur": "[ERR]"}.get(r["status"], "[?]")

        content += f"### {status_icon} #{i} — {offer['title']} @ {offer['company']}\n\n"
        content += f"- **Score match** : {offer['match_score']:.0f}/100\n"
        content += f"- **Qualité lettre** : {r.get('quality_score', 'N/A')}/100\n"
        content += f"- **Statut** : {r['status']}\n"
        content += f"- **Contrat** : {offer['contract_type']}\n"
        content += f"- **Lieu** : {offer['location']}\n"

        if r.get("email_subject"):
            content += f"- **Objet email** : {r['email_subject']}\n"

        if r.get("recipient"):
            content += f"- **Destinataire** : {r['recipient']}\n"

        content += "\n"

    report_path.write_text(content, encoding="utf-8")
    return report_path


# ── Pipeline principal ───────────────────────────────────────────────────────

def run_applicator(
    profile: UserProfile | None = None,
    send_mode: bool = False,
    recipient_email: str = "",
) -> list[dict]:
    """Pipeline complet : filtrage → génération email → envoi/simulation → rapport.

    Args:
        profile: Profil utilisateur (si None, charge le dernier).
        send_mode: Si True, envoie réellement les emails.
        recipient_email: Email de destination (pour tests, remplace le destinataire réel).

    Returns:
        Liste des résultats par candidature.
    """
    mode = "envoi réel" if send_mode else "simulation"
    logger.info("Mode : %s", mode)

    # Charger le profil
    if profile is None:
        profile = get_latest_profile()
        if profile is None:
            raise RuntimeError("Aucun profil trouvé. Lancez d'abord : python -m agents.cv_optimizer")
    logger.info("Candidat : %s (%s)", profile.full_name, profile.email)

    # Trouver le CV
    cv_path = find_cv()
    if cv_path:
        logger.info("CV trouvé : %s", cv_path.name)
    else:
        logger.warning("Aucun CV trouvé dans uploads/ — l'email sera envoyé sans CV joint.")

    # Charger les offres éligibles
    eligible = load_eligible_offers()
    if not eligible:
        logger.warning("Aucune offre éligible (score >= %d + qualité >= %d).", MIN_MATCH_SCORE, MIN_QUALITY_SCORE)
        return []

    logger.info("%d candidature(s) éligible(s)", len(eligible))

    results = []

    for i, offer in enumerate(eligible, 1):
        company = offer["company"]
        job_title = offer["title"]
        letter_path = Path(offer.pop("_letter_path"))
        quality_score = offer.pop("_quality_score", None)

        logger.info(
            "\nCandidature %d/%d : %s @ %s",
            i, len(eligible), job_title, company,
        )

        result = {
            "offer": offer,
            "quality_score": quality_score,
            "status": "erreur",
            "email_subject": "",
            "recipient": "",
        }

        try:
            # Générer l'email
            logger.info("  Génération de l'email...")
            email_data = generate_email(profile, offer)
            subject = email_data["subject"]
            body = email_data["body"]
            result["email_subject"] = subject

            # Déterminer le destinataire
            to_email = recipient_email or f"recrutement@{_guess_domain(company)}"
            result["recipient"] = to_email

            if send_mode:
                # Envoi réel
                logger.info("  Envoi à %s...", to_email)
                send_email(
                    to_email=to_email,
                    subject=subject,
                    body=body,
                    cv_path=cv_path,
                    letter_path=letter_path,
                )
                result["status"] = "envoyée"
                update_job_status(company, job_title, "envoyée")
                logger.info("  → Email envoyé avec succès")
            else:
                # Simulation
                result["status"] = "simulée"
                update_job_status(company, job_title, "simulée")
                logger.info("  → [SIMULATION] Email préparé :")
                logger.info("    De : %s", SMTP_EMAIL or profile.email)
                logger.info("    À : %s", to_email)
                logger.info("    Objet : %s", subject)
                logger.info("    CV joint : %s", cv_path.name if cv_path else "non")
                logger.info("    Lettre jointe : %s", letter_path.name)
                logger.info("    ---")
                for line in body.split("\n"):
                    logger.info("    %s", line)
                logger.info("    ---")

        except Exception as e:
            logger.error("  → Erreur : %s", e)
            result["status"] = "erreur"

        results.append(result)

    # Générer le rapport
    report_path = generate_report(results, mode)
    logger.info("\nRapport sauvegardé : %s", report_path)

    return results


def _guess_domain(company: str) -> str:
    """Devine le domaine email d'une entreprise (heuristique simple)."""
    name = company.lower().strip()
    name = re.sub(r"[''`]", "", name)
    # Cas connus
    known = {
        "bnp paribas": "bnpparibas.com",
        "société générale": "socgen.com",
        "societe generale": "socgen.com",
        "edf": "edf.fr",
        "orange": "orange.com",
        "capgemini": "capgemini.com",
        "accenture": "accenture.com",
        "l'oréal": "loreal.com",
        "loreal": "loreal.com",
        "dataiku": "dataiku.com",
    }
    for key, domain in known.items():
        if key in name:
            return domain
    # Fallback : première partie du nom
    clean = re.sub(r"[^a-z0-9]", "", name)
    return f"{clean}.com"


# ── Point d'entrée CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    send_mode = "--send" in sys.argv

    # Email de test optionnel : --to email@example.com
    recipient = ""
    if "--to" in sys.argv:
        idx = sys.argv.index("--to")
        if idx + 1 < len(sys.argv):
            recipient = sys.argv[idx + 1]

    if send_mode:
        logger.info("MODE ENVOI RÉEL — les emails seront envoyés !")
        if not SMTP_EMAIL or not SMTP_PASSWORD:
            logger.error("SMTP_EMAIL et SMTP_PASSWORD requis dans .env")
            logger.error("Configurez un mot de passe d'application Gmail :")
            logger.error("  https://myaccount.google.com/apppasswords")
            sys.exit(1)
    else:
        logger.info("Mode SIMULATION (ajoutez --send pour envoyer réellement)")

    results = run_applicator(send_mode=send_mode, recipient_email=recipient)

    if not results:
        print("\nAucune candidature éligible.")
        sys.exit(0)

    # Affichage récapitulatif
    print("\n" + "=" * 70)
    print(f"  CANDIDATURES — {len(results)} traitée(s)")
    print("=" * 70)

    for i, r in enumerate(results, 1):
        offer = r["offer"]
        status = r["status"]
        icon = {"envoyée": "[OK]", "simulée": "[SIM]", "erreur": "[ERR]"}.get(status, "[?]")

        print(f"\n{icon} #{i} — {offer['title']} @ {offer['company']}")
        print(f"      Match : {offer['match_score']:.0f}/100 | Qualité : {r.get('quality_score', 'N/A')}")
        print(f"      Statut : {status}")
        if r.get("email_subject"):
            print(f"      Objet : {r['email_subject']}")
        if r.get("recipient"):
            print(f"      Destinataire : {r['recipient']}")

    print("\n" + "=" * 70)
    print(f"  Rapport : output/applications_report.md")
    print("=" * 70)
