"""Services livraison — création/assignation d'une livraison.

Centralise la logique utilisée à la fois par la création de commande (COD /
WhatsApp) et par le webhook de paiement (commandes payées en ligne : la
livraison n'est créée qu'une fois le paiement confirmé).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def create_delivery_for_order(order, zone):
    """Crée la livraison de la commande et l'assigne à un livreur dispo de la zone.

    Idempotent : ne fait rien si une livraison existe déjà pour la commande.
    Retourne la Delivery créée, ou celle existante, ou None.
    """
    from .models import Courier, Delivery

    existing = Delivery.objects.filter(order=order).first()
    if existing:
        return existing

    delivery = Delivery.objects.create(order=order, zone=zone)
    if zone:
        courier = (
            Courier.objects.filter(is_active=True, is_available=True, zones=zone).first()
        )
        if courier:
            delivery.assign(courier)
    return delivery
