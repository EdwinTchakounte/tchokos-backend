from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from catalog.models import Product


class Order(models.Model):
    """Commande / lead capturé depuis la vitrine.

    En phase 1, la commande est principalement envoyée au commerçant via
    WhatsApp. On la persiste tout de même côté serveur pour garder la donnée
    client (un des objectifs business). Le champ ``channel`` et ``status``
    préparent l'intégration paiement (Tara Money) en phase 2.
    """

    class Channel(models.TextChoices):
        WHATSAPP = "whatsapp", _("WhatsApp")
        TARA = "tara", _("Tara Money")

    class Status(models.TextChoices):
        NEW = "new", _("Nouvelle")
        CONTACTED = "contacted", _("Client contacté")
        CONFIRMED = "confirmed", _("Confirmée")
        PAID = "paid", _("Payée")
        DELIVERED = "delivered", _("Livrée")
        CANCELLED = "cancelled", _("Annulée")

    reference = models.CharField(_("référence"), max_length=20, unique=True)
    # Client connecté à l'origine de la commande (facultatif : une commande peut
    # être passée par un visiteur anonyme via WhatsApp). Permet « Mes commandes ».
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
        verbose_name=_("client"),
    )
    customer_name = models.CharField(_("nom du client"), max_length=150)
    phone = models.CharField(_("téléphone"), max_length=30)
    email = models.EmailField(_("email"), blank=True)
    city = models.CharField(_("ville"), max_length=120, blank=True)
    address = models.CharField(_("adresse / quartier"), max_length=255, blank=True)
    note = models.TextField(_("note du client"), blank=True)

    channel = models.CharField(
        _("canal"), max_length=12, choices=Channel.choices, default=Channel.WHATSAPP
    )
    status = models.CharField(
        _("statut"), max_length=12, choices=Status.choices, default=Status.NEW
    )
    total = models.DecimalField(
        _("sous-total articles (FCFA)"), max_digits=12, decimal_places=0, default=0
    )
    delivery_fee = models.DecimalField(
        _("frais de livraison (FCFA)"), max_digits=10, decimal_places=0, default=0
    )

    # Hook paiement (rempli quand Tara Money est utilisé)
    payment_reference = models.CharField(
        _("référence paiement"), max_length=120, blank=True
    )
    payment_link = models.URLField(_("lien de paiement"), blank=True)

    # Suivi de livraison via Sendo (plateforme externe)
    sendo_shipment_id = models.CharField(_("Sendo shipment id"), max_length=40, blank=True)
    sendo_tracking_token = models.CharField(_("jeton de suivi Sendo"), max_length=40, blank=True)
    sendo_status = models.CharField(_("statut livraison Sendo"), max_length=20, blank=True)

    created_at = models.DateTimeField(_("créée le"), auto_now_add=True)
    updated_at = models.DateTimeField(_("modifiée le"), auto_now=True)

    class Meta:
        verbose_name = _("commande")
        verbose_name_plural = _("commandes")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} — {self.customer_name}"

    def recompute_total(self):
        self.total = sum(item.line_total for item in self.items.all())
        return self.total

    @property
    def grand_total(self):
        return self.total + self.delivery_fee


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(
        Product, related_name="order_items", on_delete=models.PROTECT, null=True
    )
    product_name = models.CharField(_("produit"), max_length=200)
    unit_price = models.DecimalField(_("prix unitaire"), max_digits=12, decimal_places=0)
    quantity = models.PositiveIntegerField(_("quantité"), default=1)
    size = models.CharField(_("taille"), max_length=30, blank=True)

    class Meta:
        verbose_name = _("ligne de commande")
        verbose_name_plural = _("lignes de commande")

    def __str__(self):
        return f"{self.quantity} × {self.product_name}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity
