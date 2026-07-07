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
    from .geo import get_delivery_settings, recommend_courier
    from .models import Delivery

    existing = Delivery.objects.filter(order=order).first()
    if existing:
        return existing

    delivery = Delivery.objects.create(order=order, zone=zone)
    # Assignation auto (si activée par l'admin) selon la stratégie configurée
    # (premier dispo / le plus proche). Sinon la course reste « À assigner ».
    if zone and get_delivery_settings().auto_assign:
        courier = recommend_courier(zone)
        if courier:
            delivery.assign(courier)
    return delivery
