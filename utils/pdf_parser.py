"""Extraction de texte depuis des fichiers PDF et DOCX."""

from __future__ import annotations

from pathlib import Path


def extract_text_from_pdf(file_path: str | Path) -> str:
    """Extrait le texte brut d'un fichier PDF via pdfplumber."""
    import pdfplumber

    text_parts: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


def extract_text_from_docx(file_path: str | Path) -> str:
    """Extrait le texte brut d'un fichier Word (.docx)."""
    from docx import Document

    doc = Document(file_path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_text(file_path: str | Path) -> str:
    """Extrait le texte selon l'extension du fichier."""
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(path)
    elif ext in (".docx", ".doc"):
        return extract_text_from_docx(path)
    else:
        raise ValueError(f"Format non supporté : {ext}. Utilisez PDF ou DOCX.")
