"""Connexion et gestion de la base de données — SQLite pour le MVP."""

from __future__ import annotations

import json
from pathlib import Path
from core.config import BASE_DIR
from core.models import UserProfile

DB_FILE = BASE_DIR / "profiles.json"


def save_profile(profile: UserProfile) -> Path:
    """Sauvegarde un profil utilisateur en JSON (MVP sans PostgreSQL)."""
    profiles = _load_all()
    profiles.append(profile.model_dump(mode="json"))
    DB_FILE.write_text(json.dumps(profiles, ensure_ascii=False, indent=2, default=str))
    return DB_FILE


def get_latest_profile() -> UserProfile | None:
    """Récupère le dernier profil sauvegardé."""
    profiles = _load_all()
    if not profiles:
        return None
    return UserProfile(**profiles[-1])


def _load_all() -> list[dict]:
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text())
    return []
