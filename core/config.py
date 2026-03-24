"""Configuration centralisée du projet."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Chemins
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "")

# Base de données
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'job_apply.db'}")

# LLM
LLM_MODEL = "claude-sonnet-4-20250514"
LLM_MAX_TOKENS = 4096

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
