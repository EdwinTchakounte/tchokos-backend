"""Client OpenRouter pour l'assistant Tchokos (chatbot).

Configurer ``OPENROUTER_API_KEY`` (et éventuellement ``OPENROUTER_MODEL``) dans
.env. Sans clé, l'assistant répond qu'il n'est pas encore configuré.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """Tu es l'assistant virtuel de Tchokos, le super grossiste de \
chaussures et vêtements situé à Akwa, Douala (Cameroun). Devise : « The Best, \
Made in Africa ».

Ton rôle : aider les clients de façon chaleureuse, courte et claire.

LANGUE — règle absolue : réponds TOUJOURS dans la langue du dernier message du \
client. S'il écrit en anglais, réponds entièrement en anglais. S'il écrit en \
français, réponds en français. Ne mélange jamais les deux.

Informations à connaître :
- Produits : chaussures (femmes/hommes/enfants : sneakers, talons, sandales, \
mocassins, bottes, scolaires — marques Nike, New Balance, Vans), vêtements & \
sport, sacs & bagagerie (Chrisbella, Susen), montres & bijoux, linge de maison.
- Commande : sur WhatsApp (le bouton « Commander » du site) ou via le panier.
- Paiement : Mobile Money (MTN MoMo, Orange Money) et à la livraison.
- Livraison : à Douala, expédition vers Yaoundé (Tchokos Service Express).
- Adresse : Akwa, rond-point Douche, immeuble Socsuba (en face du Faya Hôtel), Douala.
- Numéro de commande WhatsApp : +237 673 398 046.

Règles STRICTES : reste factuel. N'invente JAMAIS de prix, de stock, de \
promotion ni de modèle précis — si on te demande un prix ou une dispo exacte, \
invite chaleureusement à confirmer sur WhatsApp (+237 673 398 046). Sois concis \
(2-3 phrases max)."""


class OpenRouterError(Exception):
    pass


def is_configured() -> bool:
    return bool(getattr(settings, "OPENROUTER_API_KEY", ""))


def chat(messages: list[dict], locale: str | None = None) -> str:
    """Envoie l'historique (liste {role, content}) et renvoie la réponse texte.

    ``locale`` ("fr"/"en") force la langue de réponse — les petits modèles
    « lite » ignorent parfois la consigne du system prompt, donc on l'ancre via
    une consigne déterministe en fin d'historique.
    """
    api_key = getattr(settings, "OPENROUTER_API_KEY", "")
    if not api_key:
        return (
            "L'assistant n'est pas encore activé. En attendant, écrivez-nous sur "
            "WhatsApp au +237 673 398 046 — on vous répond vite ! 🙂"
        )

    system = SYSTEM_PROMPT
    if locale == "en":
        system += "\n\nIMPORTANT: The customer is browsing in English. Reply ONLY in English."
    elif locale == "fr":
        system += "\n\nIMPORTANT : le client navigue en français. Réponds UNIQUEMENT en français."

    model = getattr(settings, "OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct")
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}] + messages[-12:],
        "max_tokens": 400,
        "temperature": 0.5,
    }
    try:
        resp = requests.post(
            ENDPOINT,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": getattr(settings, "WAGTAILADMIN_BASE_URL", "https://tchokos-sarl.com"),
                "X-Title": "Tchokos Assistant",
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        logger.error("[OpenRouter] réseau: %s", exc)
        raise OpenRouterError(str(exc)) from exc

    if resp.status_code >= 300:
        logger.error("[OpenRouter] %s: %s", resp.status_code, resp.text[:300])
        raise OpenRouterError(f"OpenRouter {resp.status_code}")

    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()
