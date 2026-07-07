"""Crée les comptes de démo : un admin (CMS) et un client.

Idempotent. Usage : python manage.py seed_accounts
Mots de passe de démo (à changer en prod) : voir DEMO_PASSWORD.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()
DEMO_PASSWORD = "tchokos123"


class Command(BaseCommand):
    help = "Crée un compte admin (CMS) et un compte client de démo."

    def handle(self, *args, **options):
        admin, created = User.objects.get_or_create(
            email="admin@tchokos-sarl.com",
            defaults={
                "full_name": "Admin Tchokos",
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            admin.set_password(DEMO_PASSWORD)
            admin.save()
            self.stdout.write(f"  + admin admin@tchokos-sarl.com / {DEMO_PASSWORD}")
        else:
            # garantit l'accès même si le compte existait sans droits
            if not (admin.is_staff and admin.is_superuser):
                admin.is_staff = admin.is_superuser = True
                admin.role = User.Role.ADMIN
                admin.save()

        client, c_created = User.objects.get_or_create(
            email="client@tchokos-sarl.com",
            defaults={
                "full_name": "Client Démo",
                "phone": "237690000099",
                "role": User.Role.CLIENT,
            },
        )
        if c_created:
            client.set_password(DEMO_PASSWORD)
            client.save()
            self.stdout.write(f"  + client client@tchokos-sarl.com / {DEMO_PASSWORD}")

        self.stdout.write(self.style.SUCCESS(
            f"Seed comptes OK : {User.objects.count()} utilisateurs."
        ))
