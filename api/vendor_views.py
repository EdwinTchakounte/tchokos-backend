"""API de l'espace vendeur (Tchokos et ses futurs revendeurs).

Auth légère par téléphone (token signé), même approche que l'espace livreur.
Cible production : OTP SMS/WhatsApp.
"""
from django.core import signing
from django.db.models import Q, Sum
from django.utils.text import slugify
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from catalog.models import Category, Product
from orders.models import OrderItem
from vendors.models import Vendor

SALT = "tchokos-vendor-auth"
TOKEN_MAX_AGE = 60 * 60 * 24 * 30


def make_token(vendor: Vendor) -> str:
    return signing.dumps({"vid": vendor.id}, salt=SALT)


def vendor_from_request(request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        data = signing.loads(auth[7:], salt=SALT, max_age=TOKEN_MAX_AGE)
    except signing.BadSignature:
        return None
    return Vendor.objects.filter(id=data.get("vid"), is_active=True).first()


def _product_dict(p: Product, request):
    img = p.primary_image
    if img and img.image:
        image = request.build_absolute_uri(img.image.url)
    elif img and img.image_url:
        image = img.image_url
    else:
        image = p.image_url or None
    return {
        "id": p.id,
        "name": p.name,
        "slug": p.slug,
        "price": str(p.price),
        "stock_quantity": p.stock_quantity,
        "is_active": p.is_active,
        "is_featured": p.is_featured,
        "badge": p.badge,
        "target": p.target,
        "category_id": p.category_id,
        "category_name": p.category.name,
        "image": image,
    }


@api_view(["POST"])
def vendor_login(request):
    phone = (request.data.get("phone") or "").strip()
    norm = phone.replace(" ", "").lstrip("+")
    vendor = (
        Vendor.objects.filter(is_active=True)
        .filter(Q(phone=phone) | Q(phone=norm) | Q(phone="237" + norm))
        .first()
    )
    if not vendor:
        return Response(
            {"detail": "Numéro non reconnu. Contactez Tchokos pour ouvrir votre boutique."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(
        {
            "token": make_token(vendor),
            "vendor": {"id": vendor.id, "name": vendor.name, "shop_name": vendor.shop_name},
        }
    )


@api_view(["GET"])
def vendor_dashboard(request):
    vendor = vendor_from_request(request)
    if not vendor:
        return Response({"detail": "Non autorisé."}, status=status.HTTP_401_UNAUTHORIZED)

    products = vendor.products.select_related("category").prefetch_related("images")
    orders_count = (
        OrderItem.objects.filter(product__vendor=vendor)
        .values("order").distinct().count()
    )
    units = products.aggregate(s=Sum("stock_quantity"))["s"] or 0

    return Response(
        {
            "vendor": {"name": vendor.name, "shop_name": vendor.shop_name},
            "stats": {
                "products": products.count(),
                "online": products.filter(is_active=True).count(),
                "stock_units": units,
                "low_stock": products.filter(stock_quantity__lte=5, stock_quantity__gt=0).count(),
                "out_of_stock": products.filter(stock_quantity=0).count(),
                "orders": orders_count,
            },
            "categories": [
                {"id": c.id, "name": c.name}
                for c in Category.objects.filter(is_active=True)
            ],
            "products": [_product_dict(p, request) for p in products],
        }
    )


@api_view(["POST"])
def vendor_create_product(request):
    vendor = vendor_from_request(request)
    if not vendor:
        return Response({"detail": "Non autorisé."}, status=status.HTTP_401_UNAUTHORIZED)

    d = request.data
    name = (d.get("name") or "").strip()
    category = Category.objects.filter(id=d.get("category_id")).first()
    if not name or not category:
        return Response(
            {"detail": "Nom et catégorie obligatoires."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        price = int(float(d.get("price", 0)))
    except (TypeError, ValueError):
        return Response({"detail": "Prix invalide."}, status=status.HTTP_400_BAD_REQUEST)

    target = d.get("target") if d.get("target") in dict(Product.Target.choices) else Product.Target.UNISEXE

    p = Product.objects.create(
        vendor=vendor,
        category=category,
        name=name,
        price=price,
        target=target,
        description=d.get("description", ""),
        image_url=d.get("image_url", ""),
        stock_quantity=int(d.get("stock_quantity") or 0),
        is_active=True,
    )
    return Response(_product_dict(p, request), status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
def vendor_update_product(request, pk):
    vendor = vendor_from_request(request)
    if not vendor:
        return Response({"detail": "Non autorisé."}, status=status.HTTP_401_UNAUTHORIZED)
    p = Product.objects.filter(pk=pk, vendor=vendor).first()
    if not p:
        return Response({"detail": "Produit introuvable."}, status=status.HTTP_404_NOT_FOUND)

    d = request.data
    if "price" in d:
        try:
            p.price = int(float(d["price"]))
        except (TypeError, ValueError):
            return Response({"detail": "Prix invalide."}, status=status.HTTP_400_BAD_REQUEST)
    if "stock_quantity" in d:
        p.stock_quantity = max(0, int(d["stock_quantity"] or 0))
    if "is_active" in d:
        p.is_active = bool(d["is_active"])
    p.save()
    return Response(_product_dict(p, request))
