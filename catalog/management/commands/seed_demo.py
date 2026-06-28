"""Peuple la base avec le catalogue Tchokos (catégories + produits) et les
réglages de marque réels, avec de vraies images (Unsplash, via image_url).

Données calées sur une recherche web (catalogue, positionnement, contacts) —
prix alignés sur le marché grossiste de Douala. Idempotent.

Usage : python manage.py seed_demo
"""
import random

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from catalog.models import Category, Product
from siteconfig.models import BrandSettings

IMG = "https://images.unsplash.com/photo-{}?w=800&q=80&auto=format&fit=crop"

# (catégorie, description, id image Unsplash)
CATEGORIES = [
    ("Baskets & Sneakers", "Nike, New Balance, Vans… le sport et la rue à prix grossiste.", "1542291026-7eec264c27ff"),
    ("Chaussures de ville", "Mocassins, derbies et classiques pour homme.", "1614252369475-531eba835eb1"),
    ("Sandales & Claquettes", "Sandales, claquettes et tongs pour toute la famille.", "1561808843-7adeb9606939"),
    ("Chaussures femme", "Escarpins, talons et bottes tendance.", "1535043934128-cf0b28d52f95"),
    ("Chaussures enfant", "Confort et style pour les plus jeunes, et le scolaire.", "1518894781321-630e638d0742"),
    ("Vêtements homme", "Prêt-à-porter et sportswear homme.", "1547996160-81dfa63595aa"),
    ("Vêtements femme", "Robes et prêt-à-porter femme.", "1434056886845-dac89ffe9b56"),
    ("Sacs & Bagagerie", "Sacs à dos, sacs à main et valises de voyage.", "1584917865442-de89df76afd3"),
    ("Montres & Bijoux", "Montres et accessoires pour compléter la tenue.", "1523275335684-37898b6baf30"),
]

# (catégorie, nom, marque, prix, prix barré, cible, badge, id image)
PRODUCTS = [
    ("Baskets & Sneakers", "Basket sport homme Nike Air", "Nike", 15000, None, "homme", "bestseller", "1542291026-7eec264c27ff"),
    ("Baskets & Sneakers", "Sneakers New Balance 740", "New Balance", 14000, None, "unisexe", "", "1556906781-9a412961c28c"),
    ("Baskets & Sneakers", "Baskets Vans toile", "Vans", 9000, 12000, "unisexe", "promo", "1606107557195-0e29a4b5b4aa"),
    ("Baskets & Sneakers", "Sneakers femme tendance", "Tchokos", 8500, None, "femme", "nouveau", "1595950653106-6c9ebd614d3a"),
    ("Chaussures de ville", "Mocassins cuir homme marron", "Tchokos", 18000, None, "homme", "", "1614252369475-531eba835eb1"),
    ("Chaussures de ville", "Chaussures de ville derby noir", "Tchokos", 16000, 20000, "homme", "promo", "1533867617858-e7b97e060509"),
    ("Sandales & Claquettes", "Sandales femme à strass", "Tchokos", 9500, None, "femme", "nouveau", "1561808843-7adeb9606939"),
    ("Sandales & Claquettes", "Claquettes homme", "Tchokos", 6000, None, "homme", "", "1605733513597-a8f8341084e6"),
    ("Chaussures femme", "Escarpins femme talon", "Tchokos", 12000, None, "femme", "bestseller", "1535043934128-cf0b28d52f95"),
    ("Chaussures femme", "Bottes femme mi-saison", "Tchokos", 17000, 22000, "femme", "promo", "1542840410-3092f99611a3"),
    ("Chaussures enfant", "Chaussures scolaires enfant", "Tchokos", 7000, None, "enfant", "", "1518894781321-630e638d0742"),
    ("Chaussures enfant", "Baskets enfant colorées", "Tchokos", 8000, 10000, "enfant", "promo", "1606107557195-0e29a4b5b4aa"),
    ("Vêtements homme", "T-shirt sport homme", "Tchokos", 5000, None, "homme", "", "1576566588028-4147f3842f27"),
    ("Vêtements homme", "Veste / manteau homme", "Tchokos", 25000, 30000, "homme", "promo", "1591047139829-d91aecb6caea"),
    ("Vêtements femme", "Robe femme tendance", "Tchokos", 12000, None, "femme", "nouveau", "1595777457583-95e059d581b8"),
    ("Sacs & Bagagerie", "Sac à dos étudiant", "Tchokos", 9000, None, "unisexe", "", "1553062407-98eeb64c6a62"),
    ("Sacs & Bagagerie", "Sac à main femme", "Tchokos", 8000, None, "femme", "bestseller", "1584917865442-de89df76afd3"),
    ("Sacs & Bagagerie", "Set 3 valises de voyage", "Tchokos", 35000, 45000, "unisexe", "promo", "1565026057447-bc90a3dceb87"),
    ("Montres & Bijoux", "Montre homme sport", "Tchokos", 6000, None, "homme", "nouveau", "1523275335684-37898b6baf30"),
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


class Command(BaseCommand):
    help = "Catalogue Tchokos + réglages de marque (vraies images)."

    def handle(self, *args, **options):
        brand = BrandSettings.load()
        for k, v in BRAND.items():
            setattr(brand, k, v)
        brand.save()
        self.stdout.write("Réglages marque Tchokos mis à jour.")

        cat_objs = {}
        for order, (name, desc, img) in enumerate(CATEGORIES):
            cat, _ = Category.objects.update_or_create(
                slug=slugify(name),
                defaults={
                    "name": name, "description": desc,
                    "order": order, "image_url": IMG.format(img),
                },
            )
            cat_objs[name] = cat
        self.stdout.write(f"{len(CATEGORIES)} catégories prêtes.")

        rng = random.Random(42)
        for cat_name, pname, brand_name, price, compare, target, badge, img in PRODUCTS:
            is_shoe = any(k in cat_name for k in ("Chaussure", "Sneakers", "Sandales"))
            Product.objects.update_or_create(
                slug=slugify(pname),
                defaults={
                    "category": cat_objs[cat_name],
                    "name": pname,
                    "brand": brand_name,
                    "price": price,
                    "compare_at_price": compare,
                    "target": target,
                    "badge": badge,
                    "image_url": IMG.format(img),
                    "stock_quantity": rng.randint(5, 60),
                    "sizes": "39, 40, 41, 42, 43" if is_shoe else "S, M, L, XL",
                    "is_featured": rng.random() > 0.45,
                    "description": (
                        f"{pname} disponible chez Tchokos, le super grossiste d'Akwa. "
                        "Qualité et prix imbattables. Commande facile via WhatsApp, "
                        "livraison à Douala, paiement Mobile Money."
                    ),
                },
            )

        self.stdout.write(self.style.SUCCESS(
            f"Seed OK : {Category.objects.count()} catégories, "
            f"{Product.objects.count()} produits (images Unsplash)."
        ))
