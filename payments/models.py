"""Entité `Payment` — trace unique de chaque encaissement Mobile Money.

Adapté de la brique durcie « paiement » (Gathé Finance) au contexte
e-commerce Tchokos : un `Payment` est rattaché à une `Order`. On conserve la
mécanique anti-compensation (idempotency_key, reference_externe,
gateway_initiated_at) qui rend le webhook et la réconciliation rejouables
sans double-comptage.
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Payment(models.Model):
    """Pivot de tout mouvement d'argent entrant lié à une commande.

    Les champs gateway (provider_code, reference_externe…) ne sont remplis que
    pour ``source = mobile_money``. Une saisie manuelle (encaissement admin)
    reste possible avec ``source = manuel`` et ``statut = valide`` direct.
    """

    class Source(models.TextChoices):
        MOBILE_MONEY = "mobile_money", _("Mobile Money")
        MANUEL = "manuel", _("Saisie manuelle")

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", _("En attente")
        VALIDE = "valide", _("Validé")
        REJETE = "rejete", _("Rejeté")

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name=_("commande"),
    )
    # Client rattaché (facultatif : commande d'un visiteur anonyme).
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments",
    )
    montant = models.DecimalField(
        _("montant (FCFA)"), max_digits=12, decimal_places=0
    )
    source = models.CharField(
        max_length=16, choices=Source.choices, default=Source.MOBILE_MONEY, db_index=True
    )
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.EN_ATTENTE, db_index=True
    )

    # Coordonnées de l'encaissement (utile au matching webhook par téléphone).
    phone = models.CharField(_("téléphone payeur"), max_length=30, blank=True)
    network = models.CharField(_("réseau MoMo"), max_length=16, blank=True)

    # Suivi passerelle externe — rempli pour source = mobile_money.
    provider_code = models.CharField(
        max_length=24,
        blank=True,
        help_text="Clé du provider (ex. 'tara'). Vide pour une saisie manuelle.",
    )
    reference_externe = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Identifiant de transaction du provider (paymentId Tara).",
    )
    idempotency_key = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        help_text="Envoyée à Tara comme productId — empêche le double encaissement.",
    )
    gateway_initiated_at = models.DateTimeField(null=True, blank=True)
    date_validation = models.DateTimeField(null=True, blank=True)
    motif_rejet = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = _("paiement")
        verbose_name_plural = _("paiements")
        indexes = [
            models.Index(fields=["statut", "source"]),
            models.Index(fields=["order", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"#{self.pk} · {self.montant} FCFA · {self.statut}"
