"""Réception des webhooks Sendo (mises à jour de statut de livraison).

Sendo signe chaque appel en HMAC-SHA256 (en-tête X-Sendo-Signature). On vérifie
la signature, puis on met à jour le statut de suivi de la commande Tchokos.
"""
import json
import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from integrations import sendo
from orders.models import Order

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([AllowAny])  # auth = signature HMAC, pas de JWT
def sendo_webhook(request):
    signature = request.headers.get("X-Sendo-Signature", "")
    if not sendo.verify_signature(request.body, signature):
        return Response({"detail": "Signature invalide."}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return Response({"detail": "JSON invalide."}, status=status.HTTP_400_BAD_REQUEST)

    ship = payload.get("shipment", {})
    ref = ship.get("external_ref")
    new_status = ship.get("status")
    if not ref:
        return Response({"detail": "external_ref manquant."}, status=status.HTTP_400_BAD_REQUEST)

    order = Order.objects.filter(reference=ref).first()
    if order:
        order.sendo_status = new_status or order.sendo_status
        if ship.get("id") and not order.sendo_shipment_id:
            order.sendo_shipment_id = ship["id"]
        order.save(update_fields=["sendo_status", "sendo_shipment_id"])
        logger.info("[Sendo webhook] %s -> %s", ref, new_status)

    return Response({"received": True})
