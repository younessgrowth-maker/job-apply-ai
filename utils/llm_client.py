"""Client centralisé pour l'API Claude (Anthropic)."""

import anthropic
from core.config import ANTHROPIC_API_KEY, LLM_MODEL, LLM_MAX_TOKENS


def get_client() -> anthropic.Anthropic:
    """Retourne un client Anthropic configuré."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY manquante. "
            "Ajoutez-la dans le fichier .env (voir .env.example)."
        )
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def ask_claude(prompt: str, system: str = "") -> str:
    """Envoie un prompt à Claude et retourne la réponse texte."""
    client = get_client()
    messages = [{"role": "user", "content": prompt}]
    kwargs = {
        "model": LLM_MODEL,
        "max_tokens": LLM_MAX_TOKENS,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    return response.content[0].text
