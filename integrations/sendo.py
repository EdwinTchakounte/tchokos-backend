"""Connecteur Tchokos → Sendo (plateforme de suivi de livraison).

À la création d'une commande, on pousse une « livraison » vers Sendo et on
récupère le jeton de suivi public. Les mises à jour de statut reviennent par
webhook (voir api/sendo_views.py).
"""
import hashlib
import hmac
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(getattr(settings, "SENDO_API_URL", "") and getattr(settings, "SENDO_API_KEY", ""))


def create_shipment(order) -> dict | None:
    """Crée la livraison côté Sendo pour une commande Tchokos. Best-effort."""
    if not is_configured():
        return None
    payload = {
        "external_ref": order.reference,
        "recipient_name": order.customer_name,
        "recipient_phone": order.phone,
        "address_text": ", ".join(p for p in [order.address, order.city] if p),
        "cod_amount": float(order.grand_total),
        "currency": "XAF",
        "note": order.note or "",
    }
    try:
        resp = requests.post(
            f"{settings.SENDO_API_URL}/v1/shipments",
            json=payload,
            headers={"X-API-Key": settings.SENDO_API_KEY, "Content-Type": "application/json"},
            timeout=8,
        )
        if resp.status_code >= 300:
            logger.error("[Sendo] création shipment %s: %s %s", order.reference, resp.status_code, resp.text[:200])
            return None
        return resp.json()
    except requests.RequestException as exc:
        logger.error("[Sendo] réseau: %s", exc)
        return None


def verify_signature(body: bytes, signature: str) -> bool:
    """Vérifie la signature HMAC-SHA256 d'un webhook entrant."""
    secret = getattr(settings, "SENDO_WEBHOOK_SECRET", "")
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
