"""Notifications client liées à la livraison.

`send_delivery_code` envoie au **client** le code à 6 chiffres qu'il devra
remettre au livreur au moment de la livraison. Canaux pilotés par l'admin
(`BrandSettings.notify_client_email` / `notify_client_whatsapp`).

- Email : via `integrations.brevo` (canal éprouvé). Actif dès que Brevo est
  configuré.
- WhatsApp : nécessite un fournisseur d'API WhatsApp Business (Meta/Twilio/…).
  Non branché pour l'instant → simple log. Le point d'extension est prêt.

Best-effort : ne lève jamais (une notif ratée ne doit pas casser la course).
"""
from __future__ import annotations

import logging

from integrations import brevo

logger = logging.getLogger(__name__)


def _channels():
    """Canaux activés par l'admin (défaut : email seul)."""
    try:
        from siteconfig.models import BrandSettings

        s = BrandSettings.objects.first()
        if s is None:
            return True, False
        return bool(getattr(s, "notify_client_email", True)), bool(
            getattr(s, "notify_client_whatsapp", False)
        )
    except Exception:  # noqa: BLE001
        return True, False


def send_delivery_code(delivery) -> dict:
    """Envoie le code de livraison au client selon les canaux activés.

    Retourne un résumé ``{"email": bool, "whatsapp": bool}`` des canaux
    réellement déclenchés.
    """
    result = {"email": False, "whatsapp": False}
    order = delivery.order
    code = delivery.delivery_code
    if not code:
        return result

    email_on, whatsapp_on = _channels()

    if email_on and order.email:
        try:
            brevo.send_email(
                to_email=order.email,
                to_name=order.customer_name or order.email,
                subject=f"Votre code de livraison Tchokos — {order.reference}",
                html_content=(
                    f"<h2>Votre commande {order.reference} arrive 🛵</h2>"
                    "<p>Un livreur a pris en charge votre commande. Voici votre "
                    "<b>code de livraison</b> :</p>"
                    f'<p style="font-size:32px;font-weight:800;letter-spacing:6px;'
                    f'color:#0f9d58">{code}</p>'
                    "<p><b>Communiquez ce code au livreur uniquement à la "
                    "réception</b> de votre colis. Il confirme la livraison.</p>"
                    "<p style=\"font-size:12px;color:#666\">Ne partagez ce code "
                    "avec personne d'autre.</p>"
                    "<p>— L'équipe Tchokos</p>"
                ),
            )
            result["email"] = True
        except brevo.BrevoError:
            logger.exception("Échec envoi code livraison (email) %s", order.reference)

    if whatsapp_on:
        # TODO WhatsApp Business API (Meta/Twilio). Point d'extension prêt :
        # envoyer `code` au numéro `order.phone` via le fournisseur choisi.
        logger.info(
            "[delivery] canal WhatsApp activé mais fournisseur non configuré "
            "— code non envoyé par WhatsApp (%s)",
            order.reference,
        )

    logger.info(
        "[delivery] code envoyé %s — email=%s whatsapp=%s",
        order.reference, result["email"], result["whatsapp"],
    )
    return result
