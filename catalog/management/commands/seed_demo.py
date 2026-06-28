"""Peuple la base avec le catalogue Tchokos (catégories + produits) et les
réglages de marque réels (contacts, réseaux), avec images placeholder générées.

Données calées sur une recherche web (catalogue, positionnement, contacts) —
prix alignés sur le marché grossiste de Douala. À ajuster avec les vrais
visuels/prix de Tchokos. Idempotent.

Usage : python manage.py seed_demo
"""
import io
import random

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from PIL import Image, ImageDraw

from catalog.models import Category, Product, ProductImage
from siteconfig.models import BrandSettings

PALETTE = [
    (245, 158, 11), (220, 38, 38), (16, 185, 129), (37, 99, 235),
    (139, 92, 246), (236, 72, 153), (14, 165, 233), (234, 88, 12),
]

CATEGORIES = [
    ("Baskets & Sneakers", "Nike, New Balance, Vans… le sport et la rue à prix grossiste."),
    ("Chaussures de ville", "Mocassins, derbies et classiques pour homme."),
    ("Sandales & Claquettes", "Sandales, claquettes et tongs pour toute la famille."),
    ("Chaussures femme", "Escarpins, talons et bottes tendance."),
    ("Chaussures enfant", "Confort et style pour les plus jeunes, et le scolaire."),
    ("Vêtements homme", "Prêt-à-porter et sportswear homme."),
    ("Vêtements femme", "Robes et prêt-à-porter femme."),
    ("Sacs & Bagagerie", "Sacs à dos, sacs à main et valises de voyage."),
    ("Montres & Bijoux", "Montres et accessoires pour compléter la tenue."),
]

# (catégorie, nom, marque, prix, prix barré, cible, badge)
PRODUCTS = [
    ("Baskets & Sneakers", "Basket sport homme Nike Air", "Nike", 15000, None, "homme", "bestseller"),
    ("Baskets & Sneakers", "Sneakers New Balance 740", "New Balance", 14000, None, "unisexe", ""),
    ("Baskets & Sneakers", "Baskets Vans toile", "Vans", 9000, 12000, "unisexe", "promo"),
    ("Baskets & Sneakers", "Sneakers femme tendance", "Tchokos", 8500, None, "femme", "nouveau"),
    ("Chaussures de ville", "Mocassins cuir homme marron", "Tchokos", 18000, None, "homme", ""),
    ("Chaussures de ville", "Chaussures de ville derby noir", "Tchokos", 16000, 20000, "homme", "promo"),
    ("Sandales & Claquettes", "Sandales femme à strass", "Tchokos", 9500, None, "femme", "nouveau"),
    ("Sandales & Claquettes", "Claquettes homme", "Tchokos", 6000, None, "homme", ""),
    ("Chaussures femme", "Escarpins femme talon", "Tchokos", 12000, None, "femme", "bestseller"),
    ("Chaussures femme", "Bottes femme mi-saison", "Tchokos", 17000, 22000, "femme", "promo"),
    ("Chaussures enfant", "Chaussures scolaires enfant", "Tchokos", 7000, None, "enfant", ""),
    ("Chaussures enfant", "Baskets enfant colorées", "Tchokos", 8000, 10000, "enfant", "promo"),
    ("Vêtements homme", "T-shirt sport homme", "Tchokos", 5000, None, "homme", ""),
    ("Vêtements homme", "Veste / manteau homme", "Tchokos", 25000, 30000, "homme", "promo"),
    ("Vêtements femme", "Robe femme tendance", "Tchokos", 12000, None, "femme", "nouveau"),
    ("Sacs & Bagagerie", "Sac à dos étudiant", "Tchokos", 9000, None, "unisexe", ""),
    ("Sacs & Bagagerie", "Sac à main femme", "Tchokos", 8000, None, "femme", "bestseller"),
    ("Sacs & Bagagerie", "Set 3 valises de voyage", "Tchokos", 35000, 45000, "unisexe", "promo"),
    ("Montres & Bijoux", "Montre homme sport", "Tchokos", 6000, None, "homme", "nouveau"),
]

BRAND = {
    "site_name": "Tchokos",
    "tagline": "Le super grossiste chaussures & vêtements d'Akwa — « C'est difficile mais possible ».",
    "whatsapp_number": "237657945694",
    "phone": "+237 657 945 694",
    "email": "contact@tchokos.cm",  # placeholder — email public non trouvé
    "address": "Douala, Akwa, rond-point Douche, immeuble Socsuba (en face du Faya Hôtel)",
    "tiktok_url": "https://www.tiktok.com/@tchokos.sarl",
    "facebook_url": "https://www.facebook.com/tchokosgrossiste",
    "instagram_url": "https://www.instagram.com/tchokossuper",
}


def make_placeholder(label: str, color) -> ContentFile:
    img = Image.new("RGB", (800, 800), color)
    draw = ImageDraw.Draw(img)
    draw.rectangle([40, 40, 760, 760], outline=(255, 255, 255), width=6)
    draw.text((60, 700), label[:30], fill=(255, 255, 255))
    draw.text((60, 60), "TCHOKOS", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return ContentFile(buf.getvalue(), name=f"{slugify(label)}.jpg")


class Command(BaseCommand):
    help = "Catalogue Tchokos + réglages de marque (données réalistes)."

    def handle(self, *args, **options):
        # Réglages marque (force la mise à jour)
        brand = BrandSettings.load()
        for k, v in BRAND.items():
            setattr(brand, k, v)
        brand.save()
        self.stdout.write("Réglages marque Tchokos mis à jour.")

        cat_objs = {}
        for order, (name, desc) in enumerate(CATEGORIES):
            cat, created = Category.objects.get_or_create(
                slug=slugify(name),
                defaults={"name": name, "description": desc, "order": order},
            )
            cat_objs[name] = cat
            if created:
                cat.image.save(*self._img(name), save=True)
                self.stdout.write(f"  + catégorie {name}")

        rng = random.Random(42)
        for cat_name, pname, brand_name, price, compare, target, badge in PRODUCTS:
            product, created = Product.objects.get_or_create(
                slug=slugify(pname),
                defaults={
                    "category": cat_objs[cat_name],
                    "name": pname,
                    "brand": brand_name,
                    "price": price,
                    "compare_at_price": compare,
                    "target": target,
                    "badge": badge,
                    "stock_quantity": rng.randint(5, 60),
                    "sizes": "39, 40, 41, 42, 43"
                    if ("Chaussure" in cat_name or "Sneakers" in cat_name or "Sandales" in cat_name)
                    else "S, M, L, XL",
                    "is_featured": rng.random() > 0.45,
                    "description": (
                        f"{pname} disponible chez Tchokos, le super grossiste d'Akwa. "
                        "Qualité et prix imbattables. Commande facile via WhatsApp, "
                        "livraison à Douala, paiement Mobile Money."
                    ),
                },
            )
            if created:
                color = rng.choice(PALETTE)
                ProductImage.objects.create(
                    product=product, image=self._img(pname, color)[1],
                    is_primary=True, alt=pname,
                )
                self.stdout.write(f"  + produit {pname}")

        self.stdout.write(self.style.SUCCESS(
            f"Seed OK : {Category.objects.count()} catégories, "
            f"{Product.objects.count()} produits."
        ))

    def _img(self, label, color=None):
        color = color or random.choice(PALETTE)
        content = make_placeholder(label, color)
        return content.name, content
