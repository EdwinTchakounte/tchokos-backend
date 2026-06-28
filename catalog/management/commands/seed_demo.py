"""Peuple la base avec des catégories et produits de démonstration.

Génère aussi des images placeholder (Pillow) pour que la vitrine ait du visuel.
Idempotent : relançable sans dupliquer (get_or_create sur le slug).

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
    ("Chaussures Femme", "Sneakers, talons, sandales et mocassins pour elle."),
    ("Chaussures Homme", "Baskets, classiques et derbies pour lui."),
    ("Chaussures Enfant", "Confort et style pour les plus jeunes."),
    ("Vêtements", "Prêt-à-porter tendance pour toute la famille."),
    ("Accessoires", "Sacs, ceintures et compléments de tenue."),
]

PRODUCTS = [
    ("Chaussures Femme", "Sneakers Urban Blanc", "Tchokos", 18000, 25000, "femme", "promo"),
    ("Chaussures Femme", "Escarpins Soirée Noir", "Tchokos", 22000, None, "femme", "nouveau"),
    ("Chaussures Femme", "Sandales Plates Or", "Tchokos", 12000, None, "femme", ""),
    ("Chaussures Homme", "Baskets Runner Gris", "Tchokos", 20000, 28000, "homme", "promo"),
    ("Chaussures Homme", "Derbies Cuir Marron", "Tchokos", 30000, None, "homme", "bestseller"),
    ("Chaussures Homme", "Mocassins City Noir", "Tchokos", 26000, None, "homme", ""),
    ("Chaussures Enfant", "Baskets Kids Bleu", "Tchokos", 9000, 12000, "enfant", "promo"),
    ("Chaussures Enfant", "Sandales Enfant Rouge", "Tchokos", 7000, None, "enfant", "nouveau"),
    ("Vêtements", "T-shirt Made in Cameroun", "Tchokos", 6000, None, "unisexe", "made_in_cmr"),
    ("Vêtements", "Veste Légère Beige", "Tchokos", 24000, 30000, "unisexe", "promo"),
    ("Vêtements", "Robe d'été Fleurie", "Tchokos", 15000, None, "femme", "nouveau"),
    ("Accessoires", "Sac à main Cuir Camel", "Tchokos", 19000, None, "femme", "bestseller"),
    ("Accessoires", "Ceinture Classique Noir", "Tchokos", 5000, None, "homme", ""),
    ("Accessoires", "Casquette Tchokos", "Tchokos", 4000, 6000, "unisexe", "promo"),
]


def make_placeholder(label: str, color) -> ContentFile:
    img = Image.new("RGB", (800, 800), color)
    draw = ImageDraw.Draw(img)
    draw.rectangle([40, 40, 760, 760], outline=(255, 255, 255), width=6)
    draw.text((60, 700), label[:28], fill=(255, 255, 255))
    draw.text((60, 60), "TCHOKOS", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return ContentFile(buf.getvalue(), name=f"{slugify(label)}.jpg")


class Command(BaseCommand):
    help = "Crée des catégories et produits de démonstration."

    def handle(self, *args, **options):
        # Réglages marque
        brand = BrandSettings.load()
        if not brand.whatsapp_number:
            brand.whatsapp_number = "237600000000"
            brand.email = "contact@tchokos.cm"
            brand.phone = "+237 6 00 00 00 00"
            brand.tiktok_url = "https://www.tiktok.com/@tchokos"
            brand.facebook_url = "https://www.facebook.com/tchokos"
            brand.save()
            self.stdout.write("Réglages marque initialisés.")

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
                    "stock_quantity": rng.randint(3, 40),
                    "sizes": "39, 40, 41, 42, 43" if "Chaussures" in cat_name else "S, M, L, XL",
                    "is_featured": rng.random() > 0.5,
                    "description": (
                        f"{pname} signé {brand_name}. Qualité, confort et style "
                        "à prix accessible. Livraison à Douala et commande facile via WhatsApp."
                    ),
                },
            )
            if created:
                color = rng.choice(PALETTE)
                fname, content = self._img(pname, color)
                ProductImage.objects.create(
                    product=product, image=content, is_primary=True, alt=pname
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
