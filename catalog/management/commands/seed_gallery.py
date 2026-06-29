"""Ajoute plusieurs images (galerie) aux produits qui n'en ont pas.

La 1re image = l'image principale du produit (image_url), suivie de 2 vues
supplémentaires issues d'un pool Unsplash par catégorie. Idempotent.

Usage : python manage.py seed_gallery
"""
from django.core.management.base import BaseCommand

from catalog.models import Product, ProductImage

IMG = "https://images.unsplash.com/photo-{}?w=800&q=80&auto=format&fit=crop"

POOLS = {
    "baskets-sneakers": ["1542291026-7eec264c27ff", "1556906781-9a412961c28c", "1595950653106-6c9ebd614d3a", "1607522370275-f14206abe5d3"],
    "chaussures-de-ville": ["1533867617858-e7b97e060509", "1531310197839-ccf54634509e"],
    "sandales-claquettes": ["1603487742131-4160ec999306", "1543163521-1bf539c55dd2"],
    "chaussures-femme": ["1535043934128-cf0b28d52f95", "1610398752800-146f269dfcc8"],
    "chaussures-enfant": ["1514989940723-e8e51635b782", "1628253747716-0c4f5c90fdda"],
    "vetements-homme": ["1576566588028-4147f3842f27", "1591047139829-d91aecb6caea"],
    "vetements-femme": ["1595777457583-95e059d581b8", "1434056886845-dac89ffe9b56"],
    "sacs-bagagerie": ["1584917865442-de89df76afd3", "1553062407-98eeb64c6a62", "1565026057447-bc90a3dceb87"],
    "montres-bijoux": ["1523275335684-37898b6baf30"],
}


class Command(BaseCommand):
    help = "Crée des galeries multi-images pour les produits."

    def handle(self, *args, **options):
        added = 0
        for product in Product.objects.select_related("category"):
            if product.images.exists():
                continue
            pool = [IMG.format(x) for x in POOLS.get(product.category.slug, [])]
            urls = []
            if product.image_url:
                urls.append(product.image_url)
            for u in pool:
                if u not in urls:
                    urls.append(u)
                if len(urls) >= 3:
                    break
            for i, url in enumerate(urls):
                ProductImage.objects.create(
                    product=product, image_url=url, alt=product.name,
                    is_primary=(i == 0), order=i,
                )
                added += 1
        self.stdout.write(self.style.SUCCESS(
            f"Galeries créées : {added} images ajoutées."
        ))
