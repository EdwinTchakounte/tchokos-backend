"""Client Brevo (ex-Sendinblue) pour l'envoi d'emails transactionnels.

Utilise l'API HTTP v3 de Brevo (https://developers.brevo.com/).
Configurer ``BREVO_API_KEY`` dans le fichier .env.

Si la clé n'est pas configurée, les appels sont simplement loggés (no-op),
ce qui permet de développer la vitrine sans bloquer sur l'email.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


class BrevoError(Exception):
    pass


def send_email(
    *,
    to_email: str,
    to_name: str = "",
    subject: str,
    html_content: str,
    reply_to: str | None = None,
    template_id: int | None = None,
    params: dict | None = None,
):
    """Envoie un email transactionnel via Brevo.

    Si ``template_id`` est fourni, on utilise un template Brevo (avec ``params``),
    sinon on envoie ``html_content`` brut.
    """
    api_key = getattr(settings, "BREVO_API_KEY", "")
    if not api_key:
        logger.warning(
            "[Brevo] BREVO_API_KEY absente — email NON envoyé (sujet=%r, dest=%s)",
            subject, to_email,
        )
        return {"skipped": True}

    payload = {
        "sender": {
            "name": getattr(settings, "BREVO_SENDER_NAME", "Tchokos"),
            "email": getattr(settings, "BREVO_SENDER_EMAIL", "no-reply@tchokos-sarl.com"),
        },
        "to": [{"email": to_email, "name": to_name or to_email}],
        "subject": subject,
    }
    if template_id:
        payload["templateId"] = template_id
        payload["params"] = params or {}
    else:
        payload["htmlContent"] = html_content
    if reply_to:
        payload["replyTo"] = {"email": reply_to}

    try:
        resp = requests.post(
            BREVO_ENDPOINT,
            json=payload,
            headers={"api-key": api_key, "content-type": "application/json"},
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.error("[Brevo] échec réseau: %s", exc)
        raise BrevoError(str(exc)) from exc

    if resp.status_code >= 300:
        logger.error("[Brevo] erreur %s: %s", resp.status_code, resp.text)
        raise BrevoError(f"Brevo {resp.status_code}: {resp.text}")

    return resp.json() if resp.content else {"ok": True}
