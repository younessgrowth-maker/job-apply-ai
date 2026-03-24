"""Modèles de données Pydantic pour le projet."""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Experience(BaseModel):
    """Une expérience professionnelle extraite du CV."""
    title: str = Field(description="Intitulé du poste")
    company: str = Field(default="", description="Nom de l'entreprise")
    start_date: str = Field(default="", description="Date de début")
    end_date: str = Field(default="", description="Date de fin ou 'Présent'")
    description: str = Field(default="", description="Description des missions")


class Education(BaseModel):
    """Une formation extraite du CV."""
    degree: str = Field(description="Diplôme ou formation")
    institution: str = Field(default="", description="Établissement")
    year: str = Field(default="", description="Année d'obtention")


class UserProfile(BaseModel):
    """Profil structuré extrait et optimisé depuis le CV."""
    full_name: str = Field(description="Nom complet")
    email: str = Field(default="", description="Adresse email")
    phone: str = Field(default="", description="Numéro de téléphone")
    location: str = Field(default="", description="Ville / région")
    title: str = Field(default="", description="Titre professionnel cible")
    summary: str = Field(default="", description="Résumé professionnel optimisé ATS")
    skills: list[str] = Field(default_factory=list, description="Compétences clés")
    experiences: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    keywords_ats: list[str] = Field(
        default_factory=list,
        description="Mots-clés optimisés pour les systèmes ATS",
    )
    raw_text: str = Field(default="", description="Texte brut extrait du CV")
    created_at: datetime = Field(default_factory=datetime.now)


class JobOffer(BaseModel):
    """Une offre d'emploi scrapée et normalisée."""
    title: str
    company: str = ""
    location: str = ""
    description: str = ""
    url: str = ""
    source: str = ""
    contract_type: str = ""
    salary: str = ""
    match_score: float = Field(default=0.0, ge=0, le=100, description="Score de pertinence 0-100")
    scraped_at: datetime = Field(default_factory=datetime.now)


class Application(BaseModel):
    """Suivi d'une candidature."""
    job_offer: JobOffer
    cover_letter: str = ""
    status: str = Field(default="draft", description="draft|sent|viewed|replied|rejected")
    applied_at: Optional[datetime] = None
    channel: str = Field(default="", description="platform|email")
