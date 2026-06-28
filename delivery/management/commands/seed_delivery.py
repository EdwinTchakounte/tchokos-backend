"""Seed des zones de livraison (Douala) et de quelques livreurs de démo.

Idempotent. Usage : python manage.py seed_delivery
"""
from django.core.management.base import BaseCommand

from delivery.models import DeliveryZone, Courier

# (nom, frais FCFA, délai estimé min)
ZONES = [
    ("Akwa", 1000, 30),
    ("Bonanjo", 1000, 30),
    ("Bali", 1000, 35),
    ("Deïdo", 1500, 40),
    ("Bonapriso", 1500, 40),
    ("New Bell", 1500, 45),
    ("Ndokotti", 1500, 45),
    ("Bépanda", 1500, 45),
    ("Bonamoussadi", 2000, 55),
    ("Makèpè", 2000, 55),
    ("Logpom", 2500, 70),
    ("Logbessou", 2500, 70),
    ("Bonabéri", 2500, 75),
    ("Village", 2000, 60),
    ("Yassa", 3000, 80),
    ("PK (PK8–PK14)", 3000, 90),
]

COURIERS = [
    ("Patrick Mbarga", "237670000001", ["Akwa", "Bonanjo", "Bali", "Deïdo"]),
    ("Yannick Etoa", "237670000002", ["Bonamoussadi", "Makèpè", "Logpom", "Logbessou"]),
    ("Aïcha Njoya", "237670000003", ["Bonapriso", "New Bell", "Ndokotti", "Bépanda"]),
    ("Serge Kamga", "237670000004", ["Bonabéri", "Village", "Yassa", "PK (PK8–PK14)"]),
]


class Command(BaseCommand):
    help = "Crée les zones de livraison de Douala et des livreurs de démo."

    def handle(self, *args, **options):
        zone_objs = {}
        for i, (name, fee, eta) in enumerate(ZONES):
            z, created = DeliveryZone.objects.get_or_create(
                name=name, city="Douala",
                defaults={"fee": fee, "eta_minutes": eta, "order": i},
            )
            zone_objs[name] = z
            if created:
                self.stdout.write(f"  + zone {name} ({fee} FCFA)")

        for name, phone, zone_names in COURIERS:
            c, created = Courier.objects.get_or_create(
                phone=phone, defaults={"name": name}
            )
            if created:
                c.zones.set([zone_objs[z] for z in zone_names if z in zone_objs])
                self.stdout.write(f"  + livreur {name}")

        self.stdout.write(self.style.SUCCESS(
            f"Seed livraison OK : {DeliveryZone.objects.count()} zones, "
            f"{Courier.objects.count()} livreurs."
        ))
