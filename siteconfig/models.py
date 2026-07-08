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
        "Numéro WhatsApp (commande)", max_length=30, blank=True,
        help_text="Format international sans +, ex: 2376XXXXXXXX",
    )
    whatsapp_arrivages = models.CharField(
        "WhatsApp groupe arrivages", max_length=30, blank=True,
        help_text="Numéro du canal « nouveaux arrivages ». Format sans +, ex: 2376XXXXXXXX",
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

    # Notifications client (code de livraison, etc.) — pilotables par l'admin.
    notify_client_email = models.BooleanField(
        "Notifier les clients par email", default=True,
        help_text="Envoi du code de livraison et notifications au client par email (Brevo).",
    )
    notify_client_whatsapp = models.BooleanField(
        "Notifier les clients par WhatsApp", default=False,
        help_text="Nécessite un fournisseur d'API WhatsApp Business (à configurer). Sans effet tant que non branché.",
    )

    panels = [
        MultiFieldPanel(
            [FieldPanel("site_name"), FieldPanel("tagline")],
            heading="Identité",
        ),
        MultiFieldPanel(
            [
                FieldPanel("whatsapp_number"),
                FieldPanel("whatsapp_arrivages"),
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
        MultiFieldPanel(
            [
                FieldPanel("notify_client_email"),
                FieldPanel("notify_client_whatsapp"),
            ],
            heading="Notifications client",
        ),
    ]

    class Meta:
        verbose_name = "Marque & contact"


@register_setting
class DeliverySettings(BaseGenericSetting):
    """Réglages de livraison, éditables par l'admin (Wagtail → Paramètres → Livraison).

    Pilote entièrement le comportement du module de livraison : mode
    interne/externe, assignation, délais, commission, notifications.
    """

    class Mode(models.TextChoices):
        INTERNE = "internal", "Interne (livreurs Tchokos)"
        EXTERNE = "external", "Externe (prestataire)"
        MIXTE = "both", "Les deux (interne + externe)"

    class AssignStrategy(models.TextChoices):
        FIRST = "first_available", "Premier livreur disponible"
        NEAREST = "nearest", "Livreur le plus proche (distance)"

    class CommissionMode(models.TextChoices):
        FIXED = "fixed_fee", "Frais de livraison (le livreur garde les frais)"
        PERCENT = "percentage", "Pourcentage du sous-total"

    delivery_mode = models.CharField(
        "Mode de livraison", max_length=12, choices=Mode.choices, default=Mode.INTERNE,
    )
    auto_assign = models.BooleanField(
        "Assignation automatique", default=True,
        help_text="Assigner automatiquement chaque commande à un livreur. Sinon l'admin assigne à la main.",
    )
    assign_strategy = models.CharField(
        "Stratégie d'assignation", max_length=20,
        choices=AssignStrategy.choices, default=AssignStrategy.FIRST,
        help_text="« Le plus proche » nécessite les coordonnées des zones et des livreurs.",
    )
    acceptance_window_hours = models.PositiveIntegerField(
        "Délai d'acceptation (heures)", default=4,
        help_text="Temps laissé au livreur pour accepter avant expiration.",
    )
    commission_mode = models.CharField(
        "Mode de commission", max_length=12,
        choices=CommissionMode.choices, default=CommissionMode.FIXED,
    )
    commission_percent = models.DecimalField(
        "Commission (%)", max_digits=5, decimal_places=2, default=0,
        help_text="Utilisé si mode = pourcentage. Ex: 10 = 10% du sous-total.",
    )
    notify_courier = models.BooleanField(
        "Notifier le livreur d'une nouvelle course", default=True,
    )

    panels = [
        MultiFieldPanel(
            [FieldPanel("delivery_mode")],
            heading="Mode",
        ),
        MultiFieldPanel(
            [
                FieldPanel("auto_assign"),
                FieldPanel("assign_strategy"),
                FieldPanel("acceptance_window_hours"),
            ],
            heading="Assignation",
        ),
        MultiFieldPanel(
            [FieldPanel("commission_mode"), FieldPanel("commission_percent")],
            heading="Commission",
        ),
        MultiFieldPanel(
            [FieldPanel("notify_courier")],
            heading="Notifications",
        ),
    ]

    class Meta:
        verbose_name = "Livraison"
