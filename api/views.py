import logging
import secrets
from urllib.parse import quote

from django.db import transaction
from django.db.models import Q, F
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from catalog.models import Category, Product
from orders.models import Order, OrderItem
from delivery.models import DeliveryZone, Delivery, Courier
from siteconfig.models import BrandSettings
from integrations import brevo
from integrations import tara
from integrations import openrouter
from integrations import sendo

from .serializers import (
    CategorySerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    OrderCreateSerializer,
    ContactSerializer,
    DeliveryZoneSerializer,
    MyOrderSerializer,
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


@api_view(["POST"])
def chat(request):
    """Assistant Tchokos (chatbot via OpenRouter)."""
    messages = request.data.get("messages") or []
    if not isinstance(messages, list) or not messages:
        return Response({"detail": "messages requis."}, status=status.HTTP_400_BAD_REQUEST)
    # Nettoie / borne l'historique
    clean = [
        {"role": m.get("role", "user"), "content": str(m.get("content", ""))[:2000]}
        for m in messages
        if m.get("content")
    ][-12:]
    locale = request.data.get("locale")  # "fr" | "en" (transmise par le frontend bilingue)
    try:
        reply = openrouter.chat(clean, locale=locale)
    except openrouter.OpenRouterError:
        reply = (
            "Désolé, je n'arrive pas à répondre pour le moment. Écrivez-nous sur "
            "WhatsApp au +237 673 398 046 🙏"
        )
    return Response({"reply": reply})


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

    # Paiement Tara direct, sans expédition (retrait/pas de livraison)
    with_delivery = data.get("with_delivery", True)

    product_ids = [it["product_id"] for it in data["items"]]
    products = {p.id: p for p in Product.objects.filter(id__in=product_ids)}

    # Zone de livraison (optionnelle) → frais. Ignorée si paiement sans livraison.
    zone = None
    if with_delivery and data.get("zone_id"):
        zone = DeliveryZone.objects.filter(id=data["zone_id"], is_active=True).first()

    with transaction.atomic():
        order = Order.objects.create(
            reference=_generate_reference(),
            user=request.user if request.user.is_authenticated else None,
            customer_name=data["customer_name"],
            phone=data["phone"],
            city=data.get("city", "") or (zone.name if zone else ""),
            address=data.get("address", ""),
            note=data.get("note", ""),
            channel=Order.Channel.TARA if not with_delivery else Order.Channel.WHATSAPP,
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

        # Livraison interne — uniquement si la commande est à livrer.
        if with_delivery:
            # Crée la livraison et l'assigne automatiquement à un livreur de la
            # zone (démarre la fenêtre de 4h). Sinon elle reste « À assigner ».
            delivery = Delivery.objects.create(order=order, zone=zone)
            if zone:
                courier = (
                    Courier.objects.filter(is_active=True, is_available=True, zones=zone)
                    .first()
                )
                if courier:
                    delivery.assign(courier)

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

    # Paiement Tara Mobile Money — uniquement sur le canal Tara (sans livraison,
    # « Payer maintenant »). Crée un Payment tracé + pousse le STK Push. En dev
    # sans clés Tara, le provider tourne en mode mock (paiement en_attente,
    # confirmable via l'endpoint dev). Les commandes WhatsApp ne paient pas ici.
    payment_status = None
    payment_url = ""
    payment_is_stub = False
    if not with_delivery:
        from payments.services import start_order_payment
        from payments.providers.tara import TaraProvider

        payment, payment_url, _raw = start_order_payment(order, phone=order.phone)
        payment_status = payment.statut
        payment_is_stub = TaraProvider()._mock_mode
        order.payment_reference = str(payment.idempotency_key)
        if payment_url:
            order.payment_link = payment_url
        order.save(update_fields=["payment_link", "payment_reference"])

    # Pousse la livraison vers Sendo (suivi externe) — uniquement si livraison,
    # et best-effort.
    tracking_url = ""
    if with_delivery:
        shipment = sendo.create_shipment(order)
        if shipment:
            order.sendo_shipment_id = shipment.get("id", "")
            order.sendo_tracking_token = shipment.get("tracking_token", "")
            order.sendo_status = shipment.get("status", "")
            order.save(update_fields=["sendo_shipment_id", "sendo_tracking_token", "sendo_status"])
            tracking_url = shipment.get("tracking_url", "")

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
            "payment_is_stub": payment_is_stub,
            # Statut du paiement Tara (canal sans livraison). La vitrine poll
            # ensuite GET /api/payments/status/?ref=<reference>.
            "payment_status": payment_status,
            "payment_url": payment_url,
            "tracking_url": tracking_url,
            "tracking_token": order.sendo_tracking_token,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_orders(request):
    """Commandes du client connecté, pour l'espace « Mes commandes ».

    On rattache par lien direct (``user``) ET par téléphone, afin de retrouver
    aussi les commandes passées via WhatsApp avant l'ajout du lien (ou en tant
    que visiteur) dès lors que le numéro correspond au compte.
    """
    user = request.user
    cond = Q(user=user)
    if getattr(user, "phone", ""):
        cond |= Q(phone=user.phone)
    orders = (
        Order.objects.filter(cond)
        .prefetch_related("items")
        .order_by("-created_at")[:50]
    )
    return Response(MyOrderSerializer(orders, many=True).data)


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
