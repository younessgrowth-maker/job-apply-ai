"""Dashboard Streamlit — Interface utilisateur MVP.

Lancer avec : streamlit run dashboard/app.py
"""

import sys
import json
import re
import logging
from pathlib import Path
from datetime import datetime

# Ajouter la racine du projet au PYTHONPATH
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd

st.set_page_config(page_title="Job Apply AI", page_icon="🤖", layout="wide")

# ── Chemins ──────────────────────────────────────────────────────────────────
JOBS_FILE = ROOT / "jobs.json"
PROFILES_FILE = ROOT / "profiles.json"
COVER_LETTERS_DIR = ROOT / "output" / "cover_letters"
UPLOADS_DIR = ROOT / "uploads"

# ── Fonctions utilitaires ────────────────────────────────────────────────────

def load_profile():
    """Charge le dernier profil depuis profiles.json."""
    if not PROFILES_FILE.exists():
        return None
    profiles = json.loads(PROFILES_FILE.read_text())
    return profiles[-1] if profiles else None


def load_jobs():
    """Charge les offres depuis jobs.json."""
    if not JOBS_FILE.exists():
        return None
    return json.loads(JOBS_FILE.read_text())


def load_cover_letters():
    """Charge toutes les lettres de motivation générées."""
    if not COVER_LETTERS_DIR.exists():
        return []
    letters = []
    for f in sorted(COVER_LETTERS_DIR.glob("lettre_*.md")):
        content = f.read_text(encoding="utf-8")
        # Extraire le score qualité
        quality_match = re.search(r"## Revue qualité — (\d+)/100 \((\w[\w\sé]*)\)", content)
        quality_score = int(quality_match.group(1)) if quality_match else None
        verdict = quality_match.group(2) if quality_match else None
        letters.append({
            "filename": f.name,
            "content": content,
            "quality_score": quality_score,
            "verdict": verdict,
        })
    return letters


# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.title("Job Apply AI")
st.sidebar.markdown("---")
page = st.sidebar.radio(
    "Navigation",
    ["Upload CV", "Offres", "Lettres de motivation", "Candidatures", "Pipeline"],
)
st.sidebar.markdown("---")

# Indicateurs rapides dans la sidebar
profile = load_profile()
jobs_data = load_jobs()
letters = load_cover_letters()

if profile:
    st.sidebar.success(f"Profil : {profile['full_name']}")
else:
    st.sidebar.warning("Aucun profil")

if jobs_data:
    total = jobs_data.get("total_offers", 0)
    st.sidebar.info(f"Offres : {total}")
else:
    st.sidebar.info("Offres : 0")

st.sidebar.info(f"Lettres : {len(letters)}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — UPLOAD CV
# ══════════════════════════════════════════════════════════════════════════════
if page == "Upload CV":
    st.header("Upload & Analyse du CV")

    col_upload, col_profile = st.columns([1, 1])

    with col_upload:
        st.subheader("Uploader un CV")
        uploaded = st.file_uploader(
            "Glissez votre CV ici (PDF ou DOCX)",
            type=["pdf", "docx"],
        )
        if uploaded:
            tmp_path = UPLOADS_DIR / uploaded.name
            UPLOADS_DIR.mkdir(exist_ok=True)
            tmp_path.write_bytes(uploaded.getvalue())
            st.success(f"Fichier sauvegardé : {uploaded.name}")

            if st.button("Analyser et optimiser le CV", type="primary"):
                with st.spinner("Analyse du CV par l'Agent CV Optimizer..."):
                    try:
                        from agents.cv_optimizer import optimize_cv
                        result = optimize_cv(tmp_path)
                        st.success(f"CV analysé pour **{result.full_name}**")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur : {e}")

    with col_profile:
        st.subheader("Profil actuel")
        if profile:
            st.markdown(f"**{profile['full_name']}**")
            st.markdown(f"*{profile.get('title', '')}*")
            st.markdown(f"{profile.get('email', '')} | {profile.get('phone', '')}")
            st.markdown(f"{profile.get('location', '')}")

            st.markdown("---")
            st.markdown("**Résumé ATS**")
            st.markdown(profile.get("summary", "")[:500])

            st.markdown("---")
            st.markdown("**Compétences**")
            skills = profile.get("skills", [])
            # Afficher en tags
            skills_html = " ".join(
                f'<span style="background-color:#e8f0fe;padding:2px 8px;border-radius:12px;margin:2px;display:inline-block;font-size:0.85em">{s}</span>'
                for s in skills[:20]
            )
            st.markdown(skills_html, unsafe_allow_html=True)
            if len(skills) > 20:
                st.caption(f"... et {len(skills) - 20} autres")

            st.markdown("---")
            st.markdown("**Mots-clés ATS**")
            keywords = profile.get("keywords_ats", [])
            kw_html = " ".join(
                f'<span style="background-color:#fce8e6;padding:2px 8px;border-radius:12px;margin:2px;display:inline-block;font-size:0.85em">{k}</span>'
                for k in keywords
            )
            st.markdown(kw_html, unsafe_allow_html=True)

            with st.expander("Expériences"):
                for exp in profile.get("experiences", []):
                    st.markdown(f"**{exp['title']}** — {exp.get('company', '')} ({exp.get('start_date', '')} - {exp.get('end_date', '')})")
                    st.markdown(exp.get("description", "")[:300])
                    st.markdown("---")

            with st.expander("Formation"):
                for edu in profile.get("education", []):
                    st.markdown(f"**{edu['degree']}** — {edu.get('institution', '')} ({edu.get('year', '')})")

            with st.expander("JSON complet"):
                st.json(profile)
        else:
            st.info("Aucun profil. Uploadez un CV pour commencer.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — OFFRES
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Offres":
    st.header("Offres d'emploi")

    if not jobs_data:
        st.info("Aucune offre. Lancez le scraper depuis l'onglet Pipeline.")
    else:
        offers = jobs_data.get("offers", [])

        # Filtres
        col_filter1, col_filter2 = st.columns(2)
        with col_filter1:
            min_score = st.slider("Score minimum", 0, 100, 0, 5)
        with col_filter2:
            contract_types = sorted(set(o.get("contract_type", "") for o in offers))
            selected_contract = st.multiselect("Type de contrat", contract_types, default=contract_types)

        filtered = [
            o for o in offers
            if o.get("match_score", 0) >= min_score
            and o.get("contract_type", "") in selected_contract
        ]

        st.caption(f"{len(filtered)} offre(s) affichée(s) sur {len(offers)}")

        # Tableau
        if filtered:
            df = pd.DataFrame([
                {
                    "Score": f"{o['match_score']:.0f}/100",
                    "Poste": o["title"],
                    "Entreprise": o["company"],
                    "Lieu": o["location"],
                    "Contrat": o["contract_type"],
                    "Recommandation": o.get("scoring", {}).get("recommendation", ""),
                    "Salaire": o.get("salary", ""),
                }
                for o in filtered
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Détail de chaque offre
            st.markdown("---")
            for o in filtered:
                scoring = o.get("scoring", {})
                rec = scoring.get("recommendation", "")
                icon = {"postuler": "🟢", "peut-être": "🟡", "passer": "🔴"}.get(rec, "⚪")

                with st.expander(f"{icon} {o['title']} @ {o['company']} — {o['match_score']:.0f}/100"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**Lieu** : {o['location']}")
                        st.markdown(f"**Contrat** : {o['contract_type']}")
                        st.markdown(f"**Salaire** : {o.get('salary', 'Non précisé') or 'Non précisé'}")
                        st.markdown(f"**Source** : {o.get('source', '')}")
                    with col2:
                        st.markdown(f"**Recommandation** : {rec}")
                        if scoring.get("reasons"):
                            st.markdown("**Raisons** :")
                            for r in scoring["reasons"][:3]:
                                st.markdown(f"- {r[:150]}")
                        if scoring.get("missing_skills"):
                            st.markdown("**Compétences manquantes** :")
                            for m in scoring["missing_skills"][:3]:
                                st.markdown(f"- {m}")

                    st.markdown("**Description** :")
                    st.markdown(o.get("description", "")[:500])


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — LETTRES DE MOTIVATION
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Lettres de motivation":
    st.header("Lettres de motivation")

    if not letters:
        st.info("Aucune lettre générée. Lancez le pipeline depuis l'onglet Pipeline.")
    else:
        # Résumé
        cols = st.columns(3)
        cols[0].metric("Total", len(letters))
        ready = sum(1 for l in letters if l["verdict"] == "prête")
        cols[1].metric("Prêtes", ready)
        to_improve = sum(1 for l in letters if l["verdict"] and l["verdict"] != "prête")
        cols[2].metric("A améliorer", to_improve)

        st.markdown("---")

        for letter in letters:
            quality = letter["quality_score"]
            verdict = letter["verdict"]
            fname = letter["filename"]

            # Extraire entreprise et poste du nom de fichier
            parts = fname.replace("lettre_", "").replace(".md", "").split("_", 1)
            display_name = fname.replace("lettre_", "").replace(".md", "").replace("_", " ").title()

            if verdict == "prête":
                badge = f"🟢 {quality}/100 — Prête"
            elif verdict:
                badge = f"🟡 {quality}/100 — {verdict.capitalize()}"
            else:
                badge = "⚪ Non évaluée"

            with st.expander(f"{badge} | {display_name}"):
                # Extraire le texte de la lettre (entre les premiers ---)
                content = letter["content"]
                sections = content.split("---")

                if len(sections) >= 3:
                    st.markdown(sections[2].strip())
                else:
                    st.markdown(content)

                # Revue qualité
                if quality is not None:
                    st.markdown("---")
                    st.markdown(f"**Score qualité : {quality}/100**")

                    # Extraire les détails de la revue
                    details_match = re.findall(r"\| (\w+) \| (\d+)/20 \|", content)
                    if details_match:
                        detail_df = pd.DataFrame(details_match, columns=["Critère", "Score"])
                        detail_df["Score"] = detail_df["Score"].astype(int)
                        st.bar_chart(detail_df.set_index("Critère"))

                    # Suggestions
                    suggestions = re.findall(r"^- (.+)$", content.split("**Suggestions**")[-1], re.MULTILINE) if "**Suggestions**" in content else []
                    if suggestions:
                        st.markdown("**Suggestions d'amélioration** :")
                        for s in suggestions[:3]:
                            st.warning(s)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4 — CANDIDATURES
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Candidatures":
    st.header("Suivi des candidatures")

    if not jobs_data:
        st.info("Aucune donnée. Lancez le pipeline d'abord.")
    else:
        offers = jobs_data.get("offers", [])

        # Compter les statuts
        statuses = {}
        for o in offers:
            s = o.get("application_status", "non traitée")
            statuses[s] = statuses.get(s, 0) + 1

        # Métriques
        cols = st.columns(5)
        status_config = {
            "non traitée": ("Non traitées", "⚪"),
            "simulée": ("Simulées", "🔵"),
            "envoyée": ("Envoyées", "🟢"),
            "vue": ("Vues", "🟡"),
            "réponse": ("Réponses", "🟣"),
        }
        for i, (status, (label, icon)) in enumerate(status_config.items()):
            if i < len(cols):
                cols[i].metric(f"{icon} {label}", statuses.get(status, 0))

        st.markdown("---")

        # Tableau détaillé
        rows = []
        for o in offers:
            status = o.get("application_status", "non traitée")
            icon = {"simulée": "🔵", "envoyée": "🟢", "vue": "🟡", "réponse": "🟣"}.get(status, "⚪")
            rows.append({
                "Statut": f"{icon} {status}",
                "Score": f"{o['match_score']:.0f}/100",
                "Poste": o["title"],
                "Entreprise": o["company"],
                "Contrat": o["contract_type"],
                "Date": o.get("application_date", "—"),
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Timeline par candidature
        st.markdown("---")
        st.subheader("Détail par candidature")

        for o in offers:
            status = o.get("application_status", "non traitée")
            if status == "non traitée":
                continue

            score = o["match_score"]
            icon = {"simulée": "🔵", "envoyée": "🟢", "vue": "🟡", "réponse": "🟣"}.get(status, "⚪")

            with st.expander(f"{icon} {o['title']} @ {o['company']} — {status}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Score match** : {score:.0f}/100")
                    st.markdown(f"**Contrat** : {o['contract_type']}")
                    st.markdown(f"**Lieu** : {o['location']}")
                with col2:
                    st.markdown(f"**Statut** : {status}")
                    if o.get("application_date"):
                        st.markdown(f"**Date** : {o['application_date'][:16]}")

                scoring = o.get("scoring", {})
                if scoring.get("reasons"):
                    st.markdown("**Points forts** :")
                    for r in scoring["reasons"][:3]:
                        st.markdown(f"- {r[:200]}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 5 — PIPELINE
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Pipeline":
    st.header("Pipeline complet")
    st.markdown("Lancez tout le pipeline en un clic : **CV → Scraping → Lettres → Simulation**")

    # État actuel
    st.subheader("État du pipeline")
    col1, col2, col3, col4 = st.columns(4)

    has_profile = profile is not None
    has_jobs = jobs_data is not None and len(jobs_data.get("offers", [])) > 0
    has_letters = len(letters) > 0
    has_applications = jobs_data is not None and any(
        o.get("application_status") for o in jobs_data.get("offers", [])
    )

    col1.markdown(f"### {'✅' if has_profile else '⬜'}\nProfil CV")
    col2.markdown(f"### {'✅' if has_jobs else '⬜'}\nOffres scrapées")
    col3.markdown(f"### {'✅' if has_letters else '⬜'}\nLettres générées")
    col4.markdown(f"### {'✅' if has_applications else '⬜'}\nCandidatures")

    st.markdown("---")

    # Étapes individuelles
    st.subheader("Étapes individuelles")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("#### 1. Scraping des offres")
        if not has_profile:
            st.warning("Uploadez d'abord un CV dans l'onglet Upload CV.")
        else:
            if st.button("Lancer le scraper (mode démo)", type="primary", key="scraper"):
                with st.spinner("Recherche et scoring des offres..."):
                    try:
                        from agents.scraper import run_scraper
                        results = run_scraper(use_demo=True)
                        st.success(f"{len(results)} offres trouvées et scorées !")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur : {e}")

    with col_b:
        st.markdown("#### 2. Lettres de motivation")
        if not has_jobs:
            st.warning("Lancez d'abord le scraper.")
        else:
            if st.button("Générer les lettres", type="primary", key="letters"):
                with st.spinner("Génération et revue des lettres..."):
                    try:
                        from agents.cover_letter import run_cover_letters
                        results = run_cover_letters()
                        st.success(f"{len(results)} lettres générées et relues !")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur : {e}")

    col_c, col_d = st.columns(2)

    with col_c:
        st.markdown("#### 3. Simulation candidatures")
        if not has_letters:
            st.warning("Générez d'abord les lettres.")
        else:
            if st.button("Lancer la simulation", type="primary", key="applicator"):
                with st.spinner("Simulation des candidatures..."):
                    try:
                        from agents.applicator import run_applicator
                        results = run_applicator(send_mode=False)
                        st.success(f"{len(results)} candidatures simulées !")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur : {e}")

    with col_d:
        st.markdown("#### 4. Envoi réel")
        st.warning("Configurez SMTP dans .env avant d'envoyer.")
        st.button("Envoyer (bientôt)", disabled=True, key="send")

    st.markdown("---")

    # Pipeline complet
    st.subheader("Pipeline complet (tout-en-un)")
    st.markdown("Lance les étapes 1 → 2 → 3 automatiquement.")

    if not has_profile:
        st.warning("Uploadez d'abord un CV dans l'onglet Upload CV.")
    else:
        if st.button("Lancer le pipeline complet", type="primary", key="full_pipeline"):
            logging.basicConfig(level=logging.INFO)
            progress = st.progress(0, text="Démarrage...")

            try:
                # Étape 1 — Scraping
                progress.progress(10, text="Scraping des offres...")
                from agents.scraper import run_scraper
                scraper_results = run_scraper(use_demo=True)
                progress.progress(35, text=f"{len(scraper_results)} offres trouvées")

                # Étape 2 — Lettres
                progress.progress(40, text="Génération des lettres de motivation...")
                from agents.cover_letter import run_cover_letters
                letter_results = run_cover_letters()
                progress.progress(75, text=f"{len(letter_results)} lettres générées")

                # Étape 3 — Simulation
                progress.progress(80, text="Simulation des candidatures...")
                from agents.applicator import run_applicator
                app_results = run_applicator(send_mode=False)
                progress.progress(100, text="Pipeline terminé !")

                st.success(
                    f"Pipeline terminé : {len(scraper_results)} offres → "
                    f"{len(letter_results)} lettres → "
                    f"{len(app_results)} candidatures simulées"
                )
                st.balloons()
                st.rerun()

            except Exception as e:
                st.error(f"Erreur dans le pipeline : {e}")
                import traceback
                st.code(traceback.format_exc())
