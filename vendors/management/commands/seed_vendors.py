"""Crée les vendeurs (Tchokos + un revendeur de démo) et rattache les produits.

Idempotent. Usage : python manage.py seed_vendors
"""
from django.core.management.base import BaseCommand

from catalog.models import Product
from vendors.models import Vendor


class Command(BaseCommand):
    help = "Vendeurs de démo + rattachement des produits."

    def handle(self, *args, **options):
        tchokos, _ = Vendor.objects.get_or_create(
            phone="237657945694",
            defaults={
                "name": "Tchokos",
                "shop_name": "Tchokos Sarl",
                "description": "Le super grossiste chaussures & vêtements d'Akwa, Douala.",
            },
        )
        reseller, _ = Vendor.objects.get_or_create(
            phone="237680000001",
            defaults={
                "name": "Awa Ngono",
                "shop_name": "Mode Awa",
                "description": "Revendeuse partenaire Tchokos — sélection femme.",
            },
        )

        # Tous les produits sans vendeur → Tchokos
        Product.objects.filter(vendor__isnull=True).update(vendor=tchokos)

        # Quelques produits femme → revendeuse démo (pour peupler sa boutique)
        femme = Product.objects.filter(target="femme")[:3]
        for p in femme:
            p.vendor = reseller
            p.save(update_fields=["vendor"])

        self.stdout.write(self.style.SUCCESS(
            f"Vendeurs OK : {tchokos.shop_name} ({tchokos.products.count()} produits), "
            f"{reseller.shop_name} ({reseller.products.count()} produits, tel {reseller.phone})."
        ))
