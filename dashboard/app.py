"""Dashboard Streamlit — Interface utilisateur MVP.

Lancer avec : streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

# Ajouter la racine du projet au PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from agents.cv_optimizer import optimize_cv
from core.database import get_latest_profile

st.set_page_config(page_title="Job Apply AI", page_icon="📄", layout="wide")
st.title("Job Apply AI — Candidatures automatisées par IA")

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.header("Navigation")
page = st.sidebar.radio("", ["Upload CV", "Mon Profil", "Offres"])

# ── Page Upload CV ───────────────────────────────────────────────────────────
if page == "Upload CV":
    st.header("1. Uploadez votre CV")
    uploaded = st.file_uploader(
        "Glissez votre CV ici (PDF ou DOCX)",
        type=["pdf", "docx"],
    )
    if uploaded:
        # Sauvegarder temporairement
        tmp_path = Path("uploads") / uploaded.name
        tmp_path.parent.mkdir(exist_ok=True)
        tmp_path.write_bytes(uploaded.getvalue())

        if st.button("Analyser et optimiser mon CV"):
            with st.spinner("Analyse en cours..."):
                try:
                    profile = optimize_cv(tmp_path)
                    st.success(f"CV analysé pour **{profile.full_name}**")

                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("Informations")
                        st.write(f"**Titre** : {profile.title}")
                        st.write(f"**Email** : {profile.email}")
                        st.write(f"**Localisation** : {profile.location}")

                    with col2:
                        st.subheader("Compétences détectées")
                        st.write(", ".join(profile.skills))

                    st.subheader("Résumé optimisé ATS")
                    st.write(profile.summary)

                    st.subheader("Mots-clés ATS")
                    st.write(", ".join(profile.keywords_ats))

                    with st.expander("JSON complet"):
                        st.json(profile.model_dump(mode="json"))

                except Exception as e:
                    st.error(f"Erreur : {e}")

# ── Page Mon Profil ──────────────────────────────────────────────────────────
elif page == "Mon Profil":
    st.header("Mon Profil")
    profile = get_latest_profile()
    if profile:
        st.write(f"**{profile.full_name}** — {profile.title}")
        st.write(profile.summary)
        st.subheader("Compétences")
        st.write(", ".join(profile.skills))
        st.subheader("Expériences")
        for exp in profile.experiences:
            st.write(f"- **{exp.title}** chez {exp.company} ({exp.start_date} → {exp.end_date})")
    else:
        st.info("Aucun profil trouvé. Uploadez d'abord votre CV.")

# ── Page Offres ──────────────────────────────────────────────────────────────
elif page == "Offres":
    st.header("Offres d'emploi")
    st.info("Le scraping d'offres sera disponible dans la prochaine version.")
