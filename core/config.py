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

# Claude Max Proxy
USE_CLAUDE_PROXY = os.getenv("USE_CLAUDE_PROXY", "false").lower() == "true"
CLAUDE_PROXY_URL = os.getenv("CLAUDE_PROXY_URL", "http://127.0.0.1:4523")

# Base de données
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'job_apply.db'}")

# LLM
LLM_MODEL = "claude-sonnet-4-20250514"
LLM_MAX_TOKENS = 4096

# Email SMTP (Gmail)
SMTP_EMAIL = os.getenv("SMTP_EMAIL", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
