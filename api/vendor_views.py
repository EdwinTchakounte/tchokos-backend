"""CMS produits — espace ADMINISTRATEUR de Tchokos (mobile + web).

L'admin (compte ``accounts.User`` avec is_staff / role=admin, authentifié en JWT)
gère l'intégralité du catalogue : édition complète des produits + photos
(téléversement de fichier ou URL). Plus de notion de « vendeur ».
"""
from django.db.models import Sum
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response

from accounts.permissions import IsAdminRole
from catalog.models import Category, Product, ProductImage
from orders.models import Order


def _img_url(img: ProductImage, request):
    if img.image:
        return request.build_absolute_uri(img.image.url)
    return img.image_url or None


def _image_dict(img: ProductImage, request):
    return {
        "id": img.id,
        "url": _img_url(img, request),
        "is_primary": img.is_primary,
        "order": img.order,
        "alt": img.alt,
    }


def _product_dict(p: Product, request):
    images = [_image_dict(im, request) for im in p.images.all()]
    primary = next((i["url"] for i in images if i["is_primary"]), None)
    image = primary or (images[0]["url"] if images else None) or p.image_url or None
    return {
        "id": p.id,
        "name": p.name,
        "slug": p.slug,
        "brand": p.brand,
        "description": p.description,
        "price": str(p.price),
        "compare_at_price": str(p.compare_at_price) if p.compare_at_price is not None else "",
        "stock_quantity": p.stock_quantity,
        "is_active": p.is_active,
        "is_featured": p.is_featured,
        "badge": p.badge,
        "target": p.target,
        "sizes": p.sizes,
        "category_id": p.category_id,
        "category_name": p.category.name,
        "image": image,
        "image_url": p.image_url,
        "images": images,
    }


def _parse_price(value):
    """Retourne (int_or_None, ok). '' / None -> (None, True) pour effacer un prix barré."""
    if value in (None, ""):
        return None, True
    try:
        return int(float(value)), True
    except (TypeError, ValueError):
        return None, False


@api_view(["GET"])
@permission_classes([IsAdminRole])
def admin_dashboard(request):
    products = Product.objects.select_related("category").prefetch_related("images")
    units = products.aggregate(s=Sum("stock_quantity"))["s"] or 0
    return Response(
        {
            "vendor": {  # conservé pour compat front ; ici = l'admin connecté
                "name": request.user.full_name or request.user.email,
                "shop_name": "Tchokos — Catalogue",
            },
            "stats": {
                "products": products.count(),
                "online": products.filter(is_active=True).count(),
                "stock_units": units,
                "low_stock": products.filter(stock_quantity__lte=5, stock_quantity__gt=0).count(),
                "out_of_stock": products.filter(stock_quantity=0).count(),
                "orders": Order.objects.count(),
            },
            "categories": [
                {"id": c.id, "name": c.name}
                for c in Category.objects.filter(is_active=True)
            ],
            "products": [_product_dict(p, request) for p in products],
        }
    )


@api_view(["POST"])
@permission_classes([IsAdminRole])
def admin_create_product(request):
    d = request.data
    name = (d.get("name") or "").strip()
    category = Category.objects.filter(id=d.get("category_id")).first()
    if not name or not category:
        return Response({"detail": "Nom et catégorie obligatoires."}, status=status.HTTP_400_BAD_REQUEST)
    price, ok = _parse_price(d.get("price"))
    if not ok or price is None:
        return Response({"detail": "Prix invalide."}, status=status.HTTP_400_BAD_REQUEST)
    compare, ok = _parse_price(d.get("compare_at_price"))
    if not ok:
        return Response({"detail": "Prix barré invalide."}, status=status.HTTP_400_BAD_REQUEST)

    target = d.get("target") if d.get("target") in dict(Product.Target.choices) else Product.Target.UNISEXE
    badge = d.get("badge") if d.get("badge") in dict(Product.Badge.choices) else ""

    p = Product.objects.create(
        category=category,
        name=name,
        price=price,
        compare_at_price=compare,
        target=target,
        badge=badge,
        brand=d.get("brand", ""),
        sizes=d.get("sizes", ""),
        description=d.get("description", ""),
        image_url=d.get("image_url", ""),
        stock_quantity=int(d.get("stock_quantity") or 0),
        is_featured=str(d.get("is_featured", "")).lower() in ("1", "true", "on"),
        is_active=True,
    )
    return Response(_product_dict(p, request), status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAdminRole])
def admin_product_detail(request, pk):
    p = Product.objects.filter(pk=pk).first()
    if not p:
        return Response({"detail": "Produit introuvable."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        p.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    d = request.data
    if "name" in d:
        name = (d.get("name") or "").strip()
        if not name:
            return Response({"detail": "Le nom est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)
        p.name = name
    if "category_id" in d:
        category = Category.objects.filter(id=d.get("category_id")).first()
        if not category:
            return Response({"detail": "Catégorie inconnue."}, status=status.HTTP_400_BAD_REQUEST)
        p.category = category
    if "price" in d:
        price, ok = _parse_price(d["price"])
        if not ok or price is None:
            return Response({"detail": "Prix invalide."}, status=status.HTTP_400_BAD_REQUEST)
        p.price = price
    if "compare_at_price" in d:
        compare, ok = _parse_price(d["compare_at_price"])
        if not ok:
            return Response({"detail": "Prix barré invalide."}, status=status.HTTP_400_BAD_REQUEST)
        p.compare_at_price = compare
    if "stock_quantity" in d:
        p.stock_quantity = max(0, int(d["stock_quantity"] or 0))
    if "target" in d and d["target"] in dict(Product.Target.choices):
        p.target = d["target"]
    if "badge" in d and d["badge"] in dict(Product.Badge.choices):
        p.badge = d["badge"]
    if "brand" in d:
        p.brand = d["brand"] or ""
    if "sizes" in d:
        p.sizes = d["sizes"] or ""
    if "description" in d:
        p.description = d["description"] or ""
    if "image_url" in d:
        p.image_url = d["image_url"] or ""
    if "is_active" in d:
        p.is_active = d["is_active"] if isinstance(d["is_active"], bool) else str(d["is_active"]).lower() in ("1", "true", "on")
    if "is_featured" in d:
        p.is_featured = d["is_featured"] if isinstance(d["is_featured"], bool) else str(d["is_featured"]).lower() in ("1", "true", "on")
    p.save()
    return Response(_product_dict(p, request))


@api_view(["POST"])
@permission_classes([IsAdminRole])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def admin_product_images(request, pk):
    """Ajoute une photo : fichier téléversé (champ 'image') ou URL ('image_url')."""
    p = Product.objects.filter(pk=pk).first()
    if not p:
        return Response({"detail": "Produit introuvable."}, status=status.HTTP_404_NOT_FOUND)

    upload = request.FILES.get("image")
    image_url = (request.data.get("image_url") or "").strip()
    if not upload and not image_url:
        return Response({"detail": "Fournissez un fichier ou une URL d'image."}, status=status.HTTP_400_BAD_REQUEST)

    first = not p.images.exists()  # la 1re photo devient principale
    img = ProductImage(
        product=p,
        alt=(request.data.get("alt") or p.name)[:200],
        is_primary=first,
        order=p.images.count(),
    )
    if upload:
        img.image = upload
    else:
        img.image_url = image_url
    img.save()
    return Response(_image_dict(img, request), status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAdminRole])
def admin_product_image_detail(request, pk, img_pk):
    """PATCH {is_primary:true} : définit la photo principale. DELETE : supprime."""
    p = Product.objects.filter(pk=pk).first()
    if not p:
        return Response({"detail": "Produit introuvable."}, status=status.HTTP_404_NOT_FOUND)
    img = p.images.filter(pk=img_pk).first()
    if not img:
        return Response({"detail": "Photo introuvable."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        was_primary = img.is_primary
        img.delete()
        if was_primary:
            nxt = p.images.first()
            if nxt:
                nxt.is_primary = True
                nxt.save(update_fields=["is_primary"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    if request.data.get("is_primary"):
        p.images.update(is_primary=False)
        img.is_primary = True
        img.save(update_fields=["is_primary"])
    return Response(_image_dict(img, request))
