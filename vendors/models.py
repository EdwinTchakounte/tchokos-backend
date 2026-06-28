from django.db import models
from django.utils.translation import gettext_lazy as _


class Vendor(models.Model):
    """Vendeur de la plateforme (Tchokos et, à terme, ses revendeurs)."""

    name = models.CharField(_("nom du responsable"), max_length=150)
    shop_name = models.CharField(_("nom de la boutique"), max_length=150)
    phone = models.CharField(_("téléphone"), max_length=30, unique=True)
    description = models.TextField(_("description"), blank=True)
    is_active = models.BooleanField(_("actif"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("vendeur")
        verbose_name_plural = _("vendeurs")
        ordering = ["shop_name"]

    def __str__(self):
        return f"{self.shop_name} ({self.name})"
