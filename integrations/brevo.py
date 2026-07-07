"""Envoi d'emails transactionnels via Brevo — sur le backend django-anymail.

L'API publique (`send_email(...)`) est inchangée pour les appelants ; seul le
transport a changé : on construit un ``EmailMultiAlternatives`` Django qui part
par le backend ``anymail.backends.brevo`` configuré dans les settings
(``EMAIL_BACKEND`` + ``ANYMAIL['BREVO_API_KEY']``).

- En dev, ``EMAIL_BACKEND`` = console → les emails s'affichent dans les logs.
- Sans ``BREVO_API_KEY`` (et hors DEBUG), on saute l'envoi (no-op) pour ne pas
  bloquer une commande.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


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
    """Envoie un email transactionnel.

    Si ``template_id`` est fourni, on utilise un template Brevo (avec ``params``
    en variables globales), sinon on envoie ``html_content`` (+ version texte).
    """
    api_key = getattr(settings, "BREVO_API_KEY", "")
    if not api_key and not getattr(settings, "DEBUG", False):
        logger.warning(
            "[Brevo] BREVO_API_KEY absente — email NON envoyé (sujet=%r, dest=%s)",
            subject, to_email,
        )
        return {"skipped": True}

    to = f"{to_name} <{to_email}>" if to_name else to_email
    msg = EmailMultiAlternatives(
        subject=subject,
        body=strip_tags(html_content) if html_content else "",
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[to],
        reply_to=[reply_to] if reply_to else None,
    )
    if template_id:
        # Attributs reconnus par le backend Brevo d'Anymail.
        msg.template_id = template_id
        msg.merge_global_data = params or {}
    elif html_content:
        msg.attach_alternative(html_content, "text/html")

    try:
        msg.send(fail_silently=False)
    except Exception as exc:  # anymail.exceptions.* ou erreurs réseau
        logger.error("[Brevo] échec envoi (sujet=%r, dest=%s): %s", subject, to_email, exc)
        raise BrevoError(str(exc)) from exc

    return {"ok": True}
