from django.db import models

from wagtail.models import Page
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel
from wagtail.api import APIField


class HomePage(Page):
    """Page d'accueil — contenu marketing éditable par Tchokos dans Wagtail."""

    hero_title = models.CharField(
        max_length=140, blank=True,
        default="La marque chaussures & vêtements du Cameroun",
    )
    hero_subtitle = models.CharField(
        max_length=255, blank=True,
        default="Des milliers de modèles, livrés près de chez vous. Commandez en un clic sur WhatsApp.",
    )
    hero_cta_label = models.CharField(
        max_length=60, blank=True, default="Découvrir la boutique"
    )
    hero_image = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    intro = RichTextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("hero_title"),
        FieldPanel("hero_subtitle"),
        FieldPanel("hero_cta_label"),
        FieldPanel("hero_image"),
        FieldPanel("intro"),
    ]

    api_fields = [
        APIField("hero_title"),
        APIField("hero_subtitle"),
        APIField("hero_cta_label"),
        APIField("hero_image"),
        APIField("intro"),
    ]


class AboutPage(Page):
    """Page « À propos » — le récit de la marque (résilience, made in Cameroun)."""

    body = RichTextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("body"),
    ]

    api_fields = [
        APIField("body"),
    ]
