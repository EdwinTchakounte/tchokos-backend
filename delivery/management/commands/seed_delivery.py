"""Seed des zones de livraison (Douala) et de quelques livreurs de démo.

Chaque livreur a un compte User (email + mot de passe) pour se connecter.
Idempotent. Usage : python manage.py seed_delivery
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from delivery.models import DeliveryZone, Courier

User = get_user_model()
DEMO_PASSWORD = "tchokos123"

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
    ("Patrick Mbarga", "patrick@tchokos-sarl.com", "237670000001", ["Akwa", "Bonanjo", "Bali", "Deïdo"]),
    ("Yannick Etoa", "yannick@tchokos-sarl.com", "237670000002", ["Bonamoussadi", "Makèpè", "Logpom", "Logbessou"]),
    ("Aïcha Njoya", "aicha@tchokos-sarl.com", "237670000003", ["Bonapriso", "New Bell", "Ndokotti", "Bépanda"]),
    ("Serge Kamga", "serge@tchokos-sarl.com", "237670000004", ["Bonabéri", "Village", "Yassa", "PK (PK8–PK14)"]),
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

        for name, email, phone, zone_names in COURIERS:
            user, u_created = User.objects.get_or_create(
                email=email,
                defaults={"full_name": name, "phone": phone, "role": User.Role.COURIER},
            )
            if u_created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            c, created = Courier.objects.get_or_create(
                phone=phone, defaults={"name": name, "user": user}
            )
            if c.user_id != user.id:
                c.user = user
                c.save(update_fields=["user"])
            if created:
                c.zones.set([zone_objs[z] for z in zone_names if z in zone_objs])
                self.stdout.write(f"  + livreur {name} ({email})")

        self.stdout.write(self.style.SUCCESS(
            f"Seed livraison OK : {DeliveryZone.objects.count()} zones, "
            f"{Courier.objects.count()} livreurs."
        ))
