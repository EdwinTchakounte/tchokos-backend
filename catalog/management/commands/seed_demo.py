"""Peuple la base avec le catalogue RÉEL de Tchokos, calqué sur la boutique
officielle **tchokos.shop** (source de vérité).

- Catégories par cible (Homme / Femme / Enfant / Sneakers unisexe).
- 12 produits réels (Nike, Adidas, Jordan, Puma, Reebok, New Balance) aux prix
  affichés sur tchokos.shop, avec un **prix barré** pour matérialiser le
  positionnement « 🔨 on casse le prix ».
- Visuels sneakers stables (Unsplash) par défaut. Les VRAIES photos produits
  s'ajoutent ensuite via le CMS (upload → /media, auto-hébergées).
- Réglages de marque (WhatsApp, slogan, réseaux) alignés sur la boutique.

Idempotent (update_or_create par slug). Usage : python manage.py seed_demo
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils.text import slugify

from catalog.models import Category, Product
from siteconfig.models import BrandSettings

UNSPLASH = "https://images.unsplash.com/photo-{}?w=800&q=80&auto=format&fit=crop"

# (nom, description, cible, image)
CATEGORIES = [
    ("Chaussures Homme", "Sneakers Nike, Adidas & Jordan pour homme — à prix cassé.",
     "homme", UNSPLASH.format("1542291026-7eec264c27ff")),
    ("Chaussures Femme", "Élégance, tendance et confort — la sélection femme Tchokos.",
     "femme", UNSPLASH.format("1595950653106-6c9ebd614d3a")),
    ("Chaussures Enfant", "Solides, colorées et légères — pour les plus jeunes.",
     "enfant", UNSPLASH.format("1514989940723-e8e51635b782")),
    ("Sneakers Unisexe", "Les modèles cultes qui vont à tout le monde.",
     "unisexe", UNSPLASH.format("1600185365483-26d7a4cc7519")),
]

# (catégorie, nom, marque, prix, prix_barré, cible, badge, image, featured)
PRODUCTS = [
    ("Chaussures Homme", "Nike Glow Edition", "Nike", 25000, 32000, "homme", "bestseller", UNSPLASH.format("1556906781-9a412961c28c"), True),
    ("Chaussures Homme", "Nike Air Max Crystal Gold", "Nike", 35000, 45000, "homme", "bestseller", UNSPLASH.format("1518894781321-630e638d0742"), True),
    ("Chaussures Homme", "Jordan Retro Classic", "Jordan", 28000, 36000, "homme", "nouveau", UNSPLASH.format("1542291026-7eec264c27ff"), True),
    ("Chaussures Homme", "Reebok Classic Homme", "Reebok", 15000, 20000, "homme", "promo", UNSPLASH.format("1607522370275-f14206abe5d3"), False),

    ("Sneakers Unisexe", "Adidas Neon Boost", "Adidas", 22000, 28000, "unisexe", "nouveau", UNSPLASH.format("1543163521-1bf539c55dd2"), True),
    ("Sneakers Unisexe", "New Balance 574", "New Balance", 19000, 25000, "unisexe", "bestseller", UNSPLASH.format("1556906781-9a412961c28c"), True),

    ("Chaussures Femme", "Nike Air Force 1 Femme", "Nike", 20000, 27000, "femme", "nouveau", UNSPLASH.format("1595950653106-6c9ebd614d3a"), True),
    ("Chaussures Femme", "Puma Femme Élégance", "Puma", 18000, 24000, "femme", "promo", UNSPLASH.format("1543163521-1bf539c55dd2"), False),
    ("Chaussures Femme", "Puma RS-X Femme", "Puma", 17000, 23000, "femme", "nouveau", UNSPLASH.format("1600185365483-26d7a4cc7519"), False),

    ("Chaussures Enfant", "Adidas Kids Superstar", "Adidas", 12000, 16000, "enfant", "promo", UNSPLASH.format("1514989940723-e8e51635b782"), False),
    ("Chaussures Enfant", "Nike Cortez Enfant", "Nike", 10000, 14000, "enfant", "promo", UNSPLASH.format("1628253747716-0c4f5c90fdda"), False),
    ("Chaussures Enfant", "Jordan Kids", "Jordan", 13000, 18000, "enfant", "promo", UNSPLASH.format("1518894781321-630e638d0742"), False),
]

BRAND = {
    "site_name": "Tchokos",
    "tagline": "🔨 On casse le prix au marteau — Nike, Adidas & Jordan à prix grossiste.",
    "whatsapp_number": "237688094767",   # numéro de commande officiel (tchokos.shop)
    "whatsapp_arrivages": "237659360604",  # groupe WhatsApp « nouveaux arrivages »
    "phone": "+237 688 094 767",
    "email": "contact@tchokos-sarl.com",
    "address": "Douala, Akwa, rond-point Douche, immeuble Socsuba (en face du Faya Hôtel)",
    "tiktok_url": "https://www.tiktok.com/@tchokos.sarl",
    "facebook_url": "https://www.facebook.com/tchokosgrossiste",
    "instagram_url": "https://www.instagram.com/tchokossuper",
}


class Command(BaseCommand):
    help = "Catalogue réel Tchokos (calqué sur tchokos.shop) + réglages de marque."

    def handle(self, *args, **options):
        # 1) Réglages de marque
        brand = BrandSettings.load()
        for k, v in BRAND.items():
            setattr(brand, k, v)
        brand.save()
        self.stdout.write("✔ Réglages marque alignés sur tchokos.shop.")

        # 2) Catégories
        cat_objs = {}
        for order, (name, desc, target, img) in enumerate(CATEGORIES):
            cat, _ = Category.objects.update_or_create(
                slug=slugify(name),
                defaults={"name": name, "description": desc, "order": order,
                          "image_url": img, "is_active": True},
            )
            cat_objs[name] = cat
        self.stdout.write(f"✔ {len(CATEGORIES)} catégories prêtes.")

        # 3) Produits (prix cassés = compare_at_price > price → réduction affichée)
        seeded_slugs = []
        for cat_name, name, brand_name, price, compare, target, badge, img, feat in PRODUCTS:
            sizes = "28, 30, 32, 34, 36" if target == "enfant" else "39, 40, 41, 42, 43"
            slug = slugify(name)
            seeded_slugs.append(slug)
            Product.objects.update_or_create(
                slug=slug,
                defaults={
                    "category": cat_objs[cat_name],
                    "name": name,
                    "brand": brand_name,
                    "price": price,
                    "compare_at_price": compare,
                    "target": target,
                    "badge": badge,
                    "image_url": img,
                    "stock_quantity": 30,
                    "sizes": sizes,
                    "is_active": True,
                    "is_featured": feat,
                    "description": (
                        f"{name} disponible chez Tchokos, le super grossiste d'Akwa (Douala). "
                        f"Prix cassé : {price:,} FCFA au lieu de {compare:,} FCFA. "
                        "Commande facile via WhatsApp, livraison à Douala, paiement Mobile Money."
                    ).replace(",", " "),
                },
            )

        # 4) Masque les éventuels produits de test (rendu propre) sans rien supprimer.
        hidden = (
            Product.objects.filter(Q(name__icontains="test") | Q(name__icontains="démo"))
            .exclude(slug__in=seeded_slugs)
            .update(is_active=False)
        )
        if hidden:
            self.stdout.write(f"✔ {hidden} produit(s) de test masqué(s).")

        self.stdout.write(self.style.SUCCESS(
            f"Seed OK : {Category.objects.filter(is_active=True).count()} catégories, "
            f"{Product.objects.filter(is_active=True).count()} produits actifs."
        ))
