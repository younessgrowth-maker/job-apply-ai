"""Tests pour l'agent CV Optimizer."""

import json
import pytest
from unittest.mock import patch, MagicMock
from core.models import UserProfile
from agents.cv_optimizer import optimize_cv, _parse_json


# ── Tests du parsing JSON ────────────────────────────────────────────────────

class TestParseJson:
    def test_json_simple(self):
        result = _parse_json('{"name": "Test"}')
        assert result == {"name": "Test"}

    def test_json_dans_bloc_markdown(self):
        text = '```json\n{"name": "Test"}\n```'
        result = _parse_json(text)
        assert result == {"name": "Test"}

    def test_json_invalide_leve_erreur(self):
        with pytest.raises(ValueError, match="JSON valide"):
            _parse_json("ceci n'est pas du JSON")


# ── Tests du pipeline complet (avec mocks) ──────────────────────────────────

FAKE_PROFILE = {
    "full_name": "Jean Dupont",
    "email": "jean@example.com",
    "phone": "06 12 34 56 78",
    "location": "Paris",
    "title": "Data Analyst",
    "summary": "Analyste de données expérimenté",
    "skills": ["Python", "SQL", "Tableau"],
    "experiences": [
        {
            "title": "Data Analyst",
            "company": "Acme Corp",
            "start_date": "2022",
            "end_date": "Présent",
            "description": "Analyse de données clients",
        }
    ],
    "education": [
        {"degree": "Master Data Science", "institution": "Université Paris", "year": "2022"}
    ],
    "languages": ["Français (natif)", "Anglais (B2)"],
    "keywords_ats": ["data analysis", "python", "sql", "tableau", "reporting"],
}


class TestOptimizeCv:
    @patch("agents.cv_optimizer.save_profile")
    @patch("agents.cv_optimizer.ask_claude")
    @patch("agents.cv_optimizer.extract_text")
    def test_pipeline_complet(self, mock_extract, mock_claude, mock_save):
        """Vérifie que le pipeline extraction → structuration → optimisation fonctionne."""
        mock_extract.return_value = "Jean Dupont\nData Analyst\nPython, SQL"
        mock_claude.return_value = json.dumps(FAKE_PROFILE)

        # Créer un faux fichier
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"fake pdf")
            tmp_path = f.name

        result = optimize_cv(tmp_path)

        assert isinstance(result, UserProfile)
        assert result.full_name == "Jean Dupont"
        assert "Python" in result.skills
        assert mock_claude.call_count == 2  # extraction + optimisation
        mock_save.assert_called_once()

    def test_fichier_introuvable(self):
        with pytest.raises(FileNotFoundError):
            optimize_cv("/chemin/inexistant.pdf")
