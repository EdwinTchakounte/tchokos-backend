"""Géolocalisation & recommandation de livreur.

- ``haversine_km`` : distance à vol d'oiseau entre deux points GPS (sans API
  externe). Suffit pour classer les livreurs par proximité.
- ``recommend_courier`` : choisit le livreur pour une zone selon la stratégie
  configurée par l'admin (« premier dispo » ou « le plus proche »).
- ``get_delivery_settings`` : lit le singleton DeliverySettings (défauts sinon).

Le géocodage (adresse → coordonnées) est optionnel et vit dans
``integrations/geocoding.py`` (nécessite une clé Google). Ici on ne fait que du
calcul local sur des coordonnées déjà présentes.
"""
from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)


def get_delivery_settings():
    """Réglages de livraison (singleton Wagtail) ; instance par défaut si absente."""
    from siteconfig.models import DeliverySettings

    return DeliverySettings.objects.first() or DeliverySettings()


def haversine_km(lat1, lon1, lat2, lon2):
    """Distance en km entre deux points GPS. None si une coordonnée manque."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def available_couriers_for_zone(zone):
    """Livreurs actifs + disponibles couvrant la zone."""
    from .models import Courier

    if zone is None:
        return Courier.objects.none()
    return Courier.objects.filter(is_active=True, is_available=True, zones=zone)


def recommend_courier(zone, strategy: str | None = None):
    """Recommande un livreur pour la zone. Retourne un Courier ou None.

    - ``nearest`` : le livreur dispo le plus proche (coordonnées requises des
      deux côtés) ; repli sur le premier dispo si pas de coordonnées.
    - ``first_available`` (défaut) : le premier livreur dispo (ordre = nom).
    """
    qs = available_couriers_for_zone(zone)
    if not qs.exists():
        return None
    if strategy is None:
        strategy = get_delivery_settings().assign_strategy

    if (
        strategy == "nearest"
        and zone is not None
        and zone.latitude is not None
        and zone.longitude is not None
    ):
        best, best_dist = None, None
        for c in qs:
            dist = haversine_km(zone.latitude, zone.longitude, c.latitude, c.longitude)
            if dist is None:
                continue
            if best_dist is None or dist < best_dist:
                best, best_dist = c, dist
        if best is not None:
            logger.info(
                "[delivery] recommandation 'nearest' zone=%s -> %s (%.1f km)",
                getattr(zone, "name", "?"), best.name, best_dist,
            )
            return best

    return qs.first()
