import logging
import secrets
from urllib.parse import quote

from django.db import transaction
from django.db.models import Q, F
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from catalog.models import Category, Product
from orders.models import Order, OrderItem
from delivery.models import DeliveryZone, Delivery
from siteconfig.models import BrandSettings
from integrations import brevo
from integrations import tara

from .serializers import (
    CategorySerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    OrderCreateSerializer,
    ContactSerializer,
    DeliveryZoneSerializer,
)

logger = logging.getLogger(__name__)


def _fmt(amount):
    return f"{amount:,.0f}".replace(",", " ")


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CategorySerializer
    lookup_field = "slug"

    def get_queryset(self):
        return Category.objects.filter(is_active=True)


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    lookup_field = "slug"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductListSerializer

    def get_queryset(self):
        qs = (
            Product.objects.filter(is_active=True)
            .select_related("category")
            .prefetch_related("images")
        )
        params = self.request.query_params
        if category := params.get("category"):
            qs = qs.filter(category__slug=category)
        if target := params.get("target"):
            qs = qs.filter(target=target)
        if params.get("featured") in ("1", "true", "yes"):
            qs = qs.filter(is_featured=True)
        if params.get("in_stock") in ("1", "true", "yes"):
            qs = qs.filter(stock_quantity__gt=0)
        if params.get("on_sale") in ("1", "true", "yes"):
            qs = qs.filter(compare_at_price__gt=F("price"))

        # Fourchette de prix (ignore les valeurs non numériques)
        if (mn := _as_int(params.get("min_price"))) is not None:
            qs = qs.filter(price__gte=mn)
        if (mx := _as_int(params.get("max_price"))) is not None:
            qs = qs.filter(price__lte=mx)

        if search := params.get("search"):
            for term in search.split():
                qs = qs.filter(
                    Q(name__icontains=term)
                    | Q(brand__icontains=term)
                    | Q(description__icontains=term)
                    | Q(category__name__icontains=term)
                )

        # Tri
        ordering = {
            "price_asc": ("price",),
            "price_desc": ("-price",),
            "name": ("name",),
            "recent": ("-created_at",),
        }.get(params.get("sort", ""))
        if ordering:
            qs = qs.order_by(*ordering)
        return qs


@api_view(["GET"])
def site_config(request):
    s = BrandSettings.load(request_or_site=request)
    return Response({
        "site_name": s.site_name,
        "tagline": s.tagline,
        "whatsapp_number": s.whatsapp_number,
        "phone": s.phone,
        "email": s.email,
        "address": s.address,
        "social": {
            "tiktok": s.tiktok_url,
            "facebook": s.facebook_url,
            "instagram": s.instagram_url,
        },
    })


@api_view(["GET"])
def delivery_zones(request):
    zones = DeliveryZone.objects.filter(is_active=True)
    return Response(DeliveryZoneSerializer(zones, many=True).data)


def _generate_reference():
    return "TCH-" + secrets.token_hex(3).upper()


@api_view(["POST"])
def create_order(request):
    """Crée une commande (lead) et renvoie un lien WhatsApp pré-rempli.

    En phase 1, le client est redirigé vers WhatsApp avec le récapitulatif.
    La commande est persistée pour conserver la donnée client. Un lien Tara
    Money (stub) est aussi renvoyé pour préparer la phase 2.
    """
    serializer = OrderCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    product_ids = [it["product_id"] for it in data["items"]]
    products = {p.id: p for p in Product.objects.filter(id__in=product_ids)}

    # Zone de livraison (optionnelle) → frais
    zone = None
    if data.get("zone_id"):
        zone = DeliveryZone.objects.filter(id=data["zone_id"], is_active=True).first()

    with transaction.atomic():
        order = Order.objects.create(
            reference=_generate_reference(),
            customer_name=data["customer_name"],
            phone=data["phone"],
            city=data.get("city", "") or (zone.name if zone else ""),
            address=data.get("address", ""),
            note=data.get("note", ""),
            channel=Order.Channel.WHATSAPP,
            delivery_fee=zone.fee if zone else 0,
        )
        lines = []
        for it in data["items"]:
            product = products.get(it["product_id"])
            if not product:
                continue
            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                unit_price=product.price,
                quantity=it["quantity"],
                size=it.get("size", ""),
            )
            lines.append(
                f"• {it['quantity']} × {product.name}"
                + (f" (taille {it['size']})" if it.get("size") else "")
                + f" — {_fmt(product.price * it['quantity'])} FCFA"
            )
        order.recompute_total()
        order.save(update_fields=["total"])

        # Crée la livraison associée (statut « À assigner »)
        Delivery.objects.create(order=order, zone=zone)

    settings_obj = BrandSettings.load(request_or_site=request)

    # Message WhatsApp pré-rempli
    delivery_lines = ""
    if zone:
        delivery_lines = (
            f"\n\nLivraison ({zone.name}) : {_fmt(zone.fee)} FCFA"
            f"\nTotal à payer : {_fmt(order.grand_total)} FCFA"
        )
    msg = (
        f"Bonjour Tchokos 👋\nJe souhaite commander (réf {order.reference}) :\n"
        + "\n".join(lines)
        + f"\n\nSous-total : {_fmt(order.total)} FCFA"
        + delivery_lines
        + f"\nNom : {order.customer_name}"
        + (f"\nZone : {zone.name}" if zone else "")
        + (f"\nVille : {order.city}" if order.city and not zone else "")
    )
    wa_number = settings_obj.whatsapp_number or ""
    wa_link = f"https://wa.me/{wa_number}?text={quote(msg)}" if wa_number else ""

    # Hook paiement Tara (stub en phase 1)
    pay = tara.create_payment_link(
        amount=order.grand_total,
        reference=order.reference,
        description=f"Commande Tchokos {order.reference}",
        customer_phone=order.phone,
    )
    order.payment_link = pay.url
    order.payment_reference = pay.reference
    order.save(update_fields=["payment_link", "payment_reference"])

    # Email de confirmation interne via Brevo (best-effort)
    if settings_obj.email:
        try:
            brevo.send_email(
                to_email=settings_obj.email,
                to_name=settings_obj.site_name,
                subject=f"Nouvelle commande {order.reference}",
                html_content=(
                    f"<h2>Nouvelle commande {order.reference}</h2>"
                    f"<p><b>Client :</b> {order.customer_name} — {order.phone}</p>"
                    f"<p><b>Ville :</b> {order.city or '—'}</p>"
                    f"<p><b>Total :</b> {_fmt(order.total)} FCFA</p>"
                    "<ul>" + "".join(f"<li>{l}</li>" for l in lines) + "</ul>"
                ),
            )
        except brevo.BrevoError:
            logger.exception("Echec envoi email commande %s", order.reference)

    return Response(
        {
            "reference": order.reference,
            "total": order.total,
            "delivery_fee": order.delivery_fee,
            "grand_total": order.grand_total,
            "whatsapp_link": wa_link,
            "payment_link": order.payment_link,
            "payment_is_stub": pay.is_stub,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
def contact(request):
    serializer = ContactSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    settings_obj = BrandSettings.load(request_or_site=request)

    if settings_obj.email:
        try:
            brevo.send_email(
                to_email=settings_obj.email,
                to_name=settings_obj.site_name,
                subject=f"Message de contact — {data['name']}",
                reply_to=data.get("email") or None,
                html_content=(
                    f"<p><b>De :</b> {data['name']}</p>"
                    f"<p><b>Email :</b> {data.get('email') or '—'}</p>"
                    f"<p><b>Téléphone :</b> {data.get('phone') or '—'}</p>"
                    f"<p>{data['message']}</p>"
                ),
            )
        except brevo.BrevoError:
            logger.exception("Echec envoi email contact")
            return Response(
                {"detail": "Envoi impossible pour le moment."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
    return Response({"detail": "Message envoyé. Merci !"}, status=status.HTTP_201_CREATED)
