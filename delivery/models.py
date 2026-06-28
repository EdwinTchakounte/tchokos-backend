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
    """Livreur de la plateforme."""

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
    # Authentification par OTP (code envoyé par SMS/WhatsApp en prod)
    otp_code = models.CharField(_("code OTP"), max_length=6, blank=True)
    otp_expires_at = models.DateTimeField(_("OTP expire le"), null=True, blank=True)
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
