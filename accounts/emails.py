"""Emails liés au cycle de vie du compte client.

`send_account_invite` réutilise le même mécanisme de token que la
réinitialisation de mot de passe (``default_token_generator``) et la même page
front ``/mot-de-passe-oublie/confirmer`` — mais avec un message de bienvenue.
L'envoi passe par ``integrations.brevo`` (canal éprouvé, comme la notification
admin de commande), et **ne lève jamais** : un échec email ne doit pas casser
la commande.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from integrations import brevo

logger = logging.getLogger(__name__)


def build_set_password_link(user) -> str:
    """Lien d'activation : uid + token, vers la page front de définition."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    base = (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
    return f"{base}/mot-de-passe-oublie/confirmer?uid={uid}&token={token}"


def send_account_invite(user) -> None:
    """Envoie l'email de bienvenue avec le lien pour définir le mot de passe."""
    link = build_set_password_link(user)
    try:
        brevo.send_email(
            to_email=user.email,
            to_name=user.full_name or user.email,
            subject="Bienvenue chez Tchokos — activez votre compte",
            html_content=(
                "<h2>Bienvenue chez Tchokos 👋</h2>"
                "<p>Un compte a été créé automatiquement pour suivre vos "
                "commandes et vos paiements.</p>"
                "<p>Définissez votre mot de passe pour y accéder :</p>"
                f'<p><a href="{link}" '
                'style="display:inline-block;padding:12px 20px;background:#0f9d58;'
                'color:#fff;border-radius:8px;text-decoration:none">'
                "Activer mon compte</a></p>"
                f'<p style="font-size:12px;color:#666">Ou copiez ce lien :<br>{link}</p>'
                "<p>— L'équipe Tchokos</p>"
            ),
        )
    except brevo.BrevoError:
        logger.exception("Échec envoi email d'activation compte %s", user.email)
