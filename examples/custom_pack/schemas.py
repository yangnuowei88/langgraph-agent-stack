"""Schémas Pydantic pour l'exemple de pack personnalisé."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EchoInput(BaseModel):
    """Entrée du pack tutoriel : texte à transformer."""

    text: str = Field(..., min_length=1, max_length=4000, description="Texte source")


class EchoOutput(BaseModel):
    """Sortie du pack tutoriel."""

    original: str
    echoed: str
    word_count: int = Field(ge=0)
