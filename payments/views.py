"""Endpoints HTTP des paiements.

  - ``POST /api/payments/webhook/tara/``      — Tara → nous (non signé, cf. doc)
  - ``GET  /api/payments/status/?ref=TCH-…``  — polling du statut par la vitrine
  - ``POST /api/payments/dev/<ref>/confirm/`` — simule un webhook (DEBUG only)

Les vues restent minces ; le gros du travail est dans ``services.py``.
"""
from __future__ import annotations

import logging

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from orders.models import Order

from .models import Payment
from .providers import get_provider
from .providers.base import ProviderError
from .services import handle_webhook_event


logger = logging.getLogger(__name__)


def _payment_public_dict(payment: Payment) -> dict:
    """Représentation publique minimale (pas de données sensibles)."""
    return {
        "reference": payment.order.reference,
        "montant": str(payment.montant),
        "statut": payment.statut,
        "is_paid": payment.statut == Payment.Statut.VALIDE,
        "motif_rejet": payment.motif_rejet or "",
    }


# ---------------------------------------------------------------------------
# Webhook Tara (Tara → nous). Non authentifié : Tara ne signe pas. Sécurité =
# HTTPS + URL secrète + vérif businessId (dans verify_webhook).
# ---------------------------------------------------------------------------


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def webhook_tara(request):
    provider = get_provider("tara")
    try:
        event = provider.verify_webhook(request.body, request.headers.get("X-Tara-Signature", ""))
    except ProviderError as exc:
        logger.warning("[TARA] webhook rejeté : %s", exc)
        return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)

    logger.info(
        "[TARA] webhook reçu — key=%r status=%r ref=%r",
        event.payment_idempotency_key, event.status, event.provider_reference,
    )
    try:
        payment = handle_webhook_event(
            event.payment_idempotency_key,
            event.status,
            provider_reference=event.provider_reference,
            raw_payload=event.raw,
        )
    except Payment.DoesNotExist:
        # 404 pour que Tara arrête de relancer un paiement fantôme.
        return Response({"detail": "Paiement inconnu."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as exc:  # noqa: BLE001 — filet : ne jamais renvoyer 500 à Tara.
        logger.exception("[TARA] webhook handler crashed: %s", exc)
        return Response(
            {"ok": False, "error": "handler_error"}, status=status.HTTP_200_OK
        )

    return Response({"ok": True, "status": payment.statut if payment else "unknown"})


# ---------------------------------------------------------------------------
# Polling statut par la vitrine (public, par référence de commande aléatoire).
# ---------------------------------------------------------------------------


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def payment_status(request):
    ref = (request.query_params.get("ref") or "").strip()
    if not ref:
        return Response({"detail": "Paramètre ?ref= requis."}, status=status.HTTP_400_BAD_REQUEST)
    payment = (
        Payment.objects.filter(order__reference=ref)
        .select_related("order")
        .order_by("-created_at")
        .first()
    )
    if payment is None:
        return Response({"detail": "Aucun paiement pour cette commande."}, status=status.HTTP_404_NOT_FOUND)
    return Response(_payment_public_dict(payment))


# ---------------------------------------------------------------------------
# Simulateur webhook — DEBUG uniquement (tant qu'on n'a pas de tunnel Tara).
# ---------------------------------------------------------------------------


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def dev_confirm_payment(request, ref: str):
    if not settings.DEBUG:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    payment = (
        Payment.objects.filter(order__reference=ref)
        .order_by("-created_at")
        .first()
    )
    if payment is None:
        return Response({"detail": "Paiement introuvable."}, status=status.HTTP_404_NOT_FOUND)
    if payment.statut != Payment.Statut.EN_ATTENTE:
        return Response(
            {"detail": f"Paiement déjà en {payment.statut!r}."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    handle_webhook_event(
        payment.idempotency_key,
        "valide",
        provider_reference=payment.reference_externe or f"DEV-SIM-{payment.id}",
        raw_payload={"dev_simulation": True},
    )
    payment.refresh_from_db()
    return Response(_payment_public_dict(payment))
