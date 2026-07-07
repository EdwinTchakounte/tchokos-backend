import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# Fenêtre d'acceptation d'une course par le livreur (heures)
ACCEPT_WINDOW_HOURS = getattr(settings, "DELIVERY_ACCEPT_WINDOW_HOURS", 4)


class DeliveryZone(models.Model):
    """Zone de livraison (quartier de Douala) avec son tarif."""

    name = models.CharField(_("zone / quartier"), max_length=120)
    city = models.CharField(_("ville"), max_length=80, default="Douala")
    fee = models.DecimalField(
        _("frais de livraison (FCFA)"), max_digits=10, decimal_places=0, default=0
    )
    eta_minutes = models.PositiveIntegerField(
        _("délai estimé (min)"), default=60,
        help_text=_("Temps de livraison estimé en minutes."),
    )
    is_active = models.BooleanField(_("active"), default=True)
    order = models.PositiveIntegerField(_("ordre"), default=0)

    class Meta:
        verbose_name = _("zone de livraison")
        verbose_name_plural = _("zones de livraison")
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.name} ({self.fee:.0f} FCFA)"


class Courier(models.Model):
    """Profil livreur, rattaché à un compte utilisateur (accounts.User).

    L'authentification (email+mot de passe, ou OTP téléphone) est portée par le
    ``User`` ; ce modèle ne garde que les infos métier de livraison.
    """

    user = models.OneToOneField(
        "accounts.User", verbose_name=_("compte"),
        on_delete=models.CASCADE, related_name="courier_profile",
        null=True, blank=True,
    )
    name = models.CharField(_("nom"), max_length=150)
    phone = models.CharField(_("téléphone"), max_length=30, unique=True)
    city = models.CharField(_("ville"), max_length=80, default="Douala")
    vehicle = models.CharField(
        _("moyen de transport"), max_length=40, blank=True, default="Moto",
    )
    zones = models.ManyToManyField(
        DeliveryZone, blank=True, related_name="couriers",
        verbose_name=_("zones couvertes"),
    )
    is_active = models.BooleanField(_("actif"), default=True)
    is_available = models.BooleanField(_("disponible"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("livreur")
        verbose_name_plural = _("livreurs")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} — {self.phone}"


class Delivery(models.Model):
    """Cycle de vie d'une livraison, selon le scénario Tchokos :

    1. La commande est assignée à un livreur → statut ASSIGNED, le livreur a
       ``ACCEPT_WINDOW_HOURS`` (4h) pour l'accepter (``acceptance_deadline``).
    2. S'il accepte (``accept``) → statut ACCEPTED, un **code de livraison unique**
       est généré et envoyé au client (ses coordonnées aussi).
    3. À la remise, le client communique le code ; le livreur le saisit
       (``complete_with_code``) → statut COMPLETED, la commande est validée
       automatiquement (Order.status = DELIVERED).
    4. Si la fenêtre de 4h expire sans acceptation, ou si la course n'est pas
       finalisée → ``flag_for_review`` (statut EXPIRED / flagged) : ces
       livraisons sont remontées au numéro service chaque soir
       (commande ``process_deliveries``).
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("À assigner")
        ASSIGNED = "assigned", _("Assignée (attente livreur)")
        ACCEPTED = "accepted", _("Acceptée par le livreur")
        COMPLETED = "completed", _("Livrée & validée")
        EXPIRED = "expired", _("Expirée (non acceptée)")
        CANCELLED = "cancelled", _("Annulée")

    order = models.OneToOneField(
        "orders.Order", on_delete=models.CASCADE, related_name="delivery"
    )
    zone = models.ForeignKey(
        DeliveryZone, on_delete=models.PROTECT, null=True, blank=True,
        related_name="deliveries", verbose_name=_("zone"),
    )
    courier = models.ForeignKey(
        Courier, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="deliveries", verbose_name=_("livreur"),
    )
    status = models.CharField(
        _("statut"), max_length=12, choices=Status.choices, default=Status.PENDING
    )

    assigned_at = models.DateTimeField(_("assignée le"), null=True, blank=True)
    acceptance_deadline = models.DateTimeField(
        _("échéance d'acceptation"), null=True, blank=True
    )
    accepted_at = models.DateTimeField(_("acceptée le"), null=True, blank=True)
    completed_at = models.DateTimeField(_("livrée le"), null=True, blank=True)

    delivery_code = models.CharField(
        _("code de livraison"), max_length=10, blank=True,
        help_text=_("Code unique communiqué au client, saisi par le livreur."),
    )

    flagged_for_review = models.BooleanField(
        _("à vérifier (service)"), default=False,
        help_text=_("Remontée au numéro service du soir pour vérification."),
    )
    reviewed = models.BooleanField(_("vérifiée"), default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("livraison")
        verbose_name_plural = _("livraisons")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Livraison {self.order.reference} [{self.get_status_display()}]"

    # ----- transitions -----

    @staticmethod
    def _generate_code():
        # Code numérique à 6 chiffres, unique parmi les livraisons en cours
        while True:
            code = f"{secrets.randbelow(1_000_000):06d}"
            if not Delivery.objects.filter(
                delivery_code=code,
                status__in=[Delivery.Status.ACCEPTED, Delivery.Status.ASSIGNED],
            ).exists():
                return code

    def assign(self, courier: Courier):
        """Assigne la course à un livreur et démarre la fenêtre de 4h."""
        now = timezone.now()
        self.courier = courier
        self.assigned_at = now
        self.acceptance_deadline = now + timedelta(hours=ACCEPT_WINDOW_HOURS)
        self.status = self.Status.ASSIGNED
        self.flagged_for_review = False
        self.save()
        return self

    def accept(self):
        """Le livreur accepte dans les temps → génère le code pour le client."""
        if self.status != self.Status.ASSIGNED:
            raise ValueError("La course n'est pas en attente d'acceptation.")
        if self.is_overdue:
            self.expire()
            raise ValueError("Délai de 4h dépassé : course expirée.")
        self.accepted_at = timezone.now()
        self.delivery_code = self._generate_code()
        self.status = self.Status.ACCEPTED
        self.save()
        return self.delivery_code

    def complete_with_code(self, code: str) -> bool:
        """Le livreur saisit le code remis par le client → validation auto."""
        if self.status != self.Status.ACCEPTED:
            return False
        if not self.delivery_code or code.strip() != self.delivery_code:
            return False
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save()
        # Validation automatique de la commande
        self.order.status = self.order.Status.DELIVERED
        self.order.save(update_fields=["status"])
        return True

    def expire(self):
        """Fenêtre dépassée sans acceptation → à vérifier par le service."""
        self.status = self.Status.EXPIRED
        self.flagged_for_review = True
        self.save()

    @property
    def is_overdue(self) -> bool:
        return (
            self.status == self.Status.ASSIGNED
            and self.acceptance_deadline is not None
            and timezone.now() > self.acceptance_deadline
        )


class Settlement(models.Model):
    """Décaissement / règlement des fonds pour une livraison terminée.

    Deux cas selon le mode de paiement de la commande :

    - **Paiement à la livraison (cash)** : le livreur a encaissé le total du
      client. Il garde sa commission (frais de livraison) et **reverse les
      articles à la plateforme** → ``direction = courier_to_platform``,
      ``amount = total articles``.
    - **Payé en ligne (Tara)** : le client a déjà réglé ; la **plateforme doit
      la commission au livreur** → ``direction = platform_to_courier``,
      ``amount = frais de livraison``.

    Créé (idempotent) à la validation de la course, réglé manuellement depuis
    le dashboard admin.
    """

    class Direction(models.TextChoices):
        COURIER_TO_PLATFORM = "courier_to_platform", _("Livreur → plateforme")
        PLATFORM_TO_COURIER = "platform_to_courier", _("Plateforme → livreur")

    class Status(models.TextChoices):
        PENDING = "pending", _("En attente")
        SETTLED = "settled", _("Réglé")

    delivery = models.OneToOneField(
        Delivery, on_delete=models.CASCADE, related_name="settlement"
    )
    courier = models.ForeignKey(
        Courier, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="settlements",
    )
    direction = models.CharField(max_length=24, choices=Direction.choices)
    is_cod = models.BooleanField(
        _("paiement à la livraison"), default=True,
        help_text=_("True = cash encaissé par le livreur ; False = payé en ligne."),
    )
    collected = models.DecimalField(
        _("encaissé par le livreur (FCFA)"), max_digits=12, decimal_places=0, default=0
    )
    courier_fee = models.DecimalField(
        _("commission livreur (FCFA)"), max_digits=10, decimal_places=0, default=0
    )
    amount = models.DecimalField(
        _("montant à régler (FCFA)"), max_digits=12, decimal_places=0, default=0
    )
    status = models.CharField(
        _("statut"), max_length=10, choices=Status.choices, default=Status.PENDING,
        db_index=True,
    )
    settled_at = models.DateTimeField(_("réglé le"), null=True, blank=True)
    note = models.CharField(_("note"), max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("décaissement")
        verbose_name_plural = _("décaissements")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Décaissement {self.delivery.order.reference} · {self.amount} FCFA [{self.status}]"

    @classmethod
    def ensure_for_delivery(cls, delivery: "Delivery") -> "Settlement":
        """Crée le décaissement de la livraison s'il n'existe pas (idempotent)."""
        existing = cls.objects.filter(delivery=delivery).first()
        if existing:
            return existing
        order = delivery.order
        fee = order.delivery_fee or 0
        paid_online = order.payments.filter(statut="valide").exists()
        if paid_online:
            direction = cls.Direction.PLATFORM_TO_COURIER
            collected = 0
            amount = fee
            is_cod = False
        else:
            direction = cls.Direction.COURIER_TO_PLATFORM
            collected = order.grand_total
            amount = order.total
            is_cod = True
        return cls.objects.create(
            delivery=delivery,
            courier=delivery.courier,
            direction=direction,
            is_cod=is_cod,
            collected=collected,
            courier_fee=fee,
            amount=amount,
        )

    def mark_settled(self, note: str = "") -> None:
        self.status = self.Status.SETTLED
        self.settled_at = timezone.now()
        if note:
            self.note = note[:255]
        self.save(update_fields=["status", "settled_at", "note", "updated_at"])
