"""Back-office ADMIN — commandes, paiements, ventes.

Complète le CMS produits (`vendor_views`) avec la gestion des commandes et le
suivi des encaissements Tara. Réservé aux admins (`IsAdminRole`).
"""
from __future__ import annotations

import logging
from urllib.parse import quote

from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsAdminRole
from delivery.models import Delivery
from integrations import brevo
from orders.models import Order, OrderItem
from payments.models import Payment

logger = logging.getLogger(__name__)

_PAGE_SIZE_MAX = 100


def _paginate(request, default=25):
    try:
        limit = min(int(request.query_params.get("limit", default)), _PAGE_SIZE_MAX)
    except (TypeError, ValueError):
        limit = default
    try:
        offset = max(int(request.query_params.get("offset", 0)), 0)
    except (TypeError, ValueError):
        offset = 0
    return offset, limit


def _latest_payment_status(order: Order) -> str | None:
    """Statut du paiement le plus récent d'une commande (None si aucun)."""
    p = order.payments.all().order_by("-created_at").first() if hasattr(order, "payments") else None
    return p.statut if p else None


def _order_list_dict(order: Order, payment_status: str | None) -> dict:
    return {
        "id": order.id,
        "reference": order.reference,
        "customer_name": order.customer_name,
        "phone": order.phone,
        "city": order.city,
        "channel": order.channel,
        "channel_display": order.get_channel_display(),
        "status": order.status,
        "status_display": order.get_status_display(),
        "total": str(order.total),
        "delivery_fee": str(order.delivery_fee),
        "grand_total": str(order.grand_total),
        "items_count": order.items.count(),
        "payment_status": payment_status,
        "created_at": order.created_at.isoformat(),
    }


def _payment_dict(p: Payment) -> dict:
    return {
        "id": p.id,
        "montant": str(p.montant),
        "statut": p.statut,
        "statut_display": p.get_statut_display(),
        "source": p.source,
        "provider_code": p.provider_code,
        "reference_externe": p.reference_externe,
        "phone": p.phone,
        "created_at": p.created_at.isoformat(),
        "date_validation": p.date_validation.isoformat() if p.date_validation else None,
    }


def _customer_whatsapp_link(order: Order) -> str:
    """Lien wa.me pré-rempli pour recontacter le client sur sa commande."""
    digits = "".join(c for c in (order.phone or "") if c.isdigit())
    if not digits:
        return ""
    if not digits.startswith("237"):
        digits = f"237{digits.lstrip('0')}"
    msg = (
        f"Bonjour {order.customer_name} 👋\n"
        f"Au sujet de votre commande Tchokos {order.reference}…"
    )
    return f"https://wa.me/{digits}?text={quote(msg)}"


# ---------------------------------------------------------------------------
# Liste des commandes
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAdminRole])
def admin_orders(request):
    qs = Order.objects.prefetch_related("items", "payments").order_by("-created_at")

    statut = request.query_params.get("status")
    if statut:
        qs = qs.filter(status=statut)
    channel = request.query_params.get("channel")
    if channel:
        qs = qs.filter(channel=channel)
    q = (request.query_params.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(reference__icontains=q)
            | Q(customer_name__icontains=q)
            | Q(phone__icontains=q)
        )

    count = qs.count()
    offset, limit = _paginate(request)
    rows = list(qs[offset : offset + limit])
    results = [_order_list_dict(o, _latest_payment_status(o)) for o in rows]
    return Response({"count": count, "limit": limit, "offset": offset, "results": results})


# ---------------------------------------------------------------------------
# Détail + changement de statut
# ---------------------------------------------------------------------------


@api_view(["GET", "PATCH"])
@permission_classes([IsAdminRole])
def admin_order_detail(request, pk):
    order = (
        Order.objects.prefetch_related("items", "payments").filter(pk=pk).first()
    )
    if not order:
        return Response({"detail": "Commande introuvable."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PATCH":
        d = request.data
        updated = []
        if "status" in d:
            new_status = d["status"]
            if new_status not in dict(Order.Status.choices):
                return Response({"detail": "Statut invalide."}, status=status.HTTP_400_BAD_REQUEST)
            order.status = new_status
            updated.append("status")
        if "delivery_fee" in d:
            try:
                fee = int(float(d["delivery_fee"]))
                if fee < 0:
                    raise ValueError
            except (TypeError, ValueError):
                return Response({"detail": "Frais de livraison invalides."}, status=status.HTTP_400_BAD_REQUEST)
            order.delivery_fee = fee
            updated.append("delivery_fee")
        if not updated:
            return Response({"detail": "Rien à mettre à jour."}, status=status.HTTP_400_BAD_REQUEST)
        order.save(update_fields=[*updated, "updated_at"])

    items = [
        {
            "product_name": it.product_name,
            "unit_price": str(it.unit_price),
            "quantity": it.quantity,
            "size": it.size,
            "line_total": str(it.line_total),
        }
        for it in order.items.all()
    ]
    payments = [_payment_dict(p) for p in order.payments.all().order_by("-created_at")]
    return Response(
        {
            "id": order.id,
            "reference": order.reference,
            "customer_name": order.customer_name,
            "phone": order.phone,
            "email": order.user.email if order.user_id else "",
            "city": order.city,
            "address": order.address,
            "note": order.note,
            "channel": order.channel,
            "channel_display": order.get_channel_display(),
            "status": order.status,
            "status_display": order.get_status_display(),
            "status_choices": [
                {"value": v, "label": lbl} for v, lbl in Order.Status.choices
            ],
            "total": str(order.total),
            "delivery_fee": str(order.delivery_fee),
            "grand_total": str(order.grand_total),
            "created_at": order.created_at.isoformat(),
            "items": items,
            "payments": payments,
            "whatsapp_link": _customer_whatsapp_link(order),
            "tracking_token": order.sendo_tracking_token,
            "sendo_status": order.sendo_status,
        }
    )


# ---------------------------------------------------------------------------
# Contact client (email Brevo si adresse connue)
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAdminRole])
def admin_order_contact(request, pk):
    order = Order.objects.filter(pk=pk).first()
    if not order:
        return Response({"detail": "Commande introuvable."}, status=status.HTTP_404_NOT_FOUND)
    email = order.user.email if order.user_id else ""
    if not email:
        return Response(
            {
                "detail": "Aucune adresse email au dossier. Utilisez le lien WhatsApp.",
                "whatsapp_link": _customer_whatsapp_link(order),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    subject = (request.data.get("subject") or f"Votre commande Tchokos {order.reference}").strip()[:180]
    message = (request.data.get("message") or "").strip()
    if not message:
        return Response({"detail": "Message vide."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        brevo.send_email(
            to_email=email,
            to_name=order.customer_name,
            subject=subject,
            html_content=(
                f"<p>Bonjour {order.customer_name},</p>"
                f"<p>{message.replace(chr(10), '<br>')}</p>"
                f"<p style='color:#94a3b8;font-size:13px'>Commande {order.reference} — Tchokos</p>"
            ),
        )
    except brevo.BrevoError:
        logger.exception("Echec envoi email contact commande %s", order.reference)
        return Response({"detail": "Échec de l'envoi de l'email."}, status=status.HTTP_502_BAD_GATEWAY)
    return Response({"ok": True, "sent_to": email})


# ---------------------------------------------------------------------------
# Liste des paiements
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAdminRole])
def admin_payments(request):
    qs = Payment.objects.select_related("order").order_by("-created_at")
    statut = request.query_params.get("statut")
    if statut:
        qs = qs.filter(statut=statut)
    q = (request.query_params.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(order__reference__icontains=q)
            | Q(reference_externe__icontains=q)
            | Q(phone__icontains=q)
        )
    count = qs.count()
    offset, limit = _paginate(request)
    rows = list(qs[offset : offset + limit])
    results = []
    for p in rows:
        data = _payment_dict(p)
        data["order_reference"] = p.order.reference
        data["customer_name"] = p.order.customer_name
        results.append(data)
    return Response({"count": count, "limit": limit, "offset": offset, "results": results})


# ---------------------------------------------------------------------------
# Stats commandes + ventes (chiffre d'affaires encaissé)
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAdminRole])
def admin_sales_stats(request):
    orders = Order.objects.all()
    by_status = {
        row["status"]: row["n"]
        for row in orders.values("status").annotate(n=Count("id"))
    }
    # CA encaissé = somme des paiements validés.
    revenue = Payment.objects.filter(statut=Payment.Statut.VALIDE).aggregate(
        s=Sum("montant")
    )["s"] or 0
    paid_orders = orders.filter(status=Order.Status.PAID).count()
    total_orders = orders.count()
    avg_basket = (
        (Payment.objects.filter(statut=Payment.Statut.VALIDE).aggregate(s=Sum("montant"))["s"] or 0)
        / max(Payment.objects.filter(statut=Payment.Statut.VALIDE).count(), 1)
    )
    return Response(
        {
            "total_orders": total_orders,
            "orders_by_status": by_status,
            "paid_orders": paid_orders,
            "revenue_collected": str(int(revenue)),
            "avg_basket": str(int(avg_basket)),
            "payments_valides": Payment.objects.filter(statut=Payment.Statut.VALIDE).count(),
            "payments_en_attente": Payment.objects.filter(statut=Payment.Statut.EN_ATTENTE).count(),
        }
    )


@api_view(["GET"])
@permission_classes([IsAdminRole])
def admin_overview(request):
    """Vue d'ensemble : KPIs + répartition par statut + séries 30 jours + livraison.

    Une seule requête pour alimenter le tableau de bord. Toutes les valeurs
    monétaires sont des entiers XAF sérialisés en chaîne.
    """
    try:
        days = int(request.query_params.get("days", 30))
    except (TypeError, ValueError):
        days = 30
    if days not in (7, 30, 90):
        days = 30
    now = timezone.now()
    start = (now - timedelta(days=days - 1)).date()  # fenêtre glissante (aujourd'hui inclus)

    orders = Order.objects.all()
    by_status = {
        row["status"]: row["n"]
        for row in orders.values("status").annotate(n=Count("id"))
    }

    valid_payments = Payment.objects.filter(statut=Payment.Statut.VALIDE)
    revenue = valid_payments.aggregate(s=Sum("montant"))["s"] or 0
    n_valid = valid_payments.count()
    avg_basket = int(revenue / max(n_valid, 1))

    # Séries journalières (30 j), trous comblés à 0.
    orders_by_day = {
        r["d"]: r["n"]
        for r in orders.filter(created_at__date__gte=start)
        .annotate(d=TruncDate("created_at")).values("d").annotate(n=Count("id"))
    }
    rev_by_day = {
        r["d"]: int(r["s"] or 0)
        for r in valid_payments.filter(date_validation__date__gte=start)
        .annotate(d=TruncDate("date_validation")).values("d").annotate(s=Sum("montant"))
    }
    series = []
    for i in range(days):
        day = start + timedelta(days=i)
        series.append({
            "date": day.isoformat(),
            "orders": orders_by_day.get(day, 0),
            "revenue": rev_by_day.get(day, 0),
        })

    deliveries = Delivery.objects.all()
    delivery_kpis = {
        "pending": deliveries.filter(status=Delivery.Status.PENDING).count(),
        "assigned": deliveries.filter(status=Delivery.Status.ASSIGNED).count(),
        "in_progress": deliveries.filter(status=Delivery.Status.ACCEPTED).count(),
        "completed": deliveries.filter(status=Delivery.Status.COMPLETED).count(),
        "expired": deliveries.filter(status=Delivery.Status.EXPIRED).count(),
    }

    return Response({
        "kpis": {
            "revenue_collected": str(int(revenue)),
            "total_orders": orders.count(),
            "paid_orders": orders.filter(status=Order.Status.PAID).count(),
            "delivered_orders": orders.filter(status=Order.Status.DELIVERED).count(),
            "avg_basket": str(avg_basket),
            "payments_valides": n_valid,
            "payments_en_attente": Payment.objects.filter(statut=Payment.Statut.EN_ATTENTE).count(),
        },
        "days": days,
        "orders_by_status": by_status,
        "status_labels": {s.value: str(s.label) for s in Order.Status},
        "timeseries": series,
        "delivery": delivery_kpis,
    })
