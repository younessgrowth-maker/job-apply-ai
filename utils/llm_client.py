"""Client centralisé pour l'API Claude (Anthropic).

Supporte deux modes :
- API directe Anthropic (ANTHROPIC_API_KEY requise)
- Claude Max Proxy local (utilise l'abonnement Max via claude-code-proxy)
"""

import anthropic
from core.config import (
    ANTHROPIC_API_KEY, LLM_MODEL, LLM_MAX_TOKENS,
    USE_CLAUDE_PROXY, CLAUDE_PROXY_URL,
)


def get_client() -> anthropic.Anthropic:
    """Retourne un client Anthropic configuré.

    Si USE_CLAUDE_PROXY=true, utilise le proxy local (pas besoin de clé API).
    Sinon, utilise l'API Anthropic directe.
    """
    if USE_CLAUDE_PROXY:
        return anthropic.Anthropic(
            api_key="max-proxy",
            base_url=CLAUDE_PROXY_URL,
        )
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
