"""Génère des avis clients de démonstration pour les produits.

Idempotent (ne recrée pas si le produit a déjà des avis). Déterministe.
Usage : python manage.py seed_reviews
"""
import random

from django.core.management.base import BaseCommand

from catalog.models import Product, Review

NAMES = [
    "Aline M.", "Brice T.", "Carine N.", "Daniel O.", "Estelle K.", "Franck B.",
    "Ghislaine A.", "Hervé M.", "Ines P.", "Joseph N.", "Larissa F.", "Marc E.",
    "Nadège T.", "Olivier K.", "Patricia M.", "Rodrigue B.", "Sandrine O.", "Yann D.",
]

COMMENTS_5 = [
    "Qualité au top, livré rapidement à Douala. Je recommande !",
    "Exactement comme sur la photo, très satisfait. Merci Tchokos 🙏",
    "Super produit et bon prix. Commande via WhatsApp trop simple.",
    "Le livreur était à l'heure, paiement Mobile Money sans souci.",
    "Très bonne finition, taille parfaite. Je reviendrai !",
    "Rien à dire, la référence à Akwa. Service rapide.",
]
COMMENTS_4 = [
    "Bon produit dans l'ensemble, livraison un peu lente mais ça vaut le coup.",
    "Conforme à la description, j'aurais aimé plus de choix de tailles.",
    "Bonne qualité pour le prix. Service client réactif sur WhatsApp.",
    "Satisfaite de mon achat, emballage correct.",
]


class Command(BaseCommand):
    help = "Avis clients de démonstration."

    def handle(self, *args, **options):
        rng = random.Random(2026)
        created = 0
        for product in Product.objects.all():
            if product.reviews.exists():
                continue
            n = rng.randint(2, 6)
            chosen = rng.sample(NAMES, n)
            for name in chosen:
                rating = rng.choices([5, 4, 3], weights=[7, 3, 1])[0]
                comment = rng.choice(COMMENTS_5 if rating == 5 else COMMENTS_4)
                Review.objects.create(
                    product=product, author_name=name,
                    rating=rating, comment=comment,
                )
                created += 1
        self.stdout.write(self.style.SUCCESS(
            f"Avis créés : {created} (total {Review.objects.count()})."
        ))
