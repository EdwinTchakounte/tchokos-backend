from django.db import models
from wagtail.contrib.settings.models import BaseGenericSetting, register_setting
from wagtail.admin.panels import FieldPanel, MultiFieldPanel


@register_setting
class BrandSettings(BaseGenericSetting):
    """Réglages globaux de la marque, éditables dans Wagtail par l'équipe Tchokos.

    Accessible dans Wagtail : Paramètres → Marque & contact.
    Exposé au frontend via l'endpoint /api/site-config/.
    """

    # Identité
    site_name = models.CharField("Nom du site", max_length=100, default="Tchokos")
    tagline = models.CharField(
        "Accroche", max_length=200, blank=True,
        default="Chaussures & vêtements — la marque du Cameroun",
    )

    # Contact
    whatsapp_number = models.CharField(
        "Numéro WhatsApp", max_length=30, blank=True,
        help_text="Format international sans +, ex: 2376XXXXXXXX",
    )
    phone = models.CharField("Téléphone", max_length=30, blank=True)
    email = models.EmailField("Email de contact", blank=True)
    address = models.CharField(
        "Adresse", max_length=255, blank=True,
        default="Akwa, en face du Faya Hôtel, immeuble Socsuba — Douala",
    )

    # Réseaux sociaux
    tiktok_url = models.URLField("TikTok", blank=True)
    facebook_url = models.URLField("Facebook", blank=True)
    instagram_url = models.URLField("Instagram", blank=True)

    panels = [
        MultiFieldPanel(
            [FieldPanel("site_name"), FieldPanel("tagline")],
            heading="Identité",
        ),
        MultiFieldPanel(
            [
                FieldPanel("whatsapp_number"),
                FieldPanel("phone"),
                FieldPanel("email"),
                FieldPanel("address"),
            ],
            heading="Contact",
        ),
        MultiFieldPanel(
            [
                FieldPanel("tiktok_url"),
                FieldPanel("facebook_url"),
                FieldPanel("instagram_url"),
            ],
            heading="Réseaux sociaux",
        ),
    ]

    class Meta:
        verbose_name = "Marque & contact"
