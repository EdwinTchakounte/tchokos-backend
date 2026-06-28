"""API de l'espace livreur.

Authentification légère par numéro de téléphone (token signé, sans mot de passe)
— suffisant pour la démo / phase 1. La cible production est l'OTP SMS/WhatsApp
(déjà prévu dans la vision plateforme).
"""
from django.core import signing
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from delivery.models import Courier, Delivery

SALT = "tchokos-courier-auth"
TOKEN_MAX_AGE = 60 * 60 * 24 * 30  # 30 jours


def make_token(courier: Courier) -> str:
    return signing.dumps({"cid": courier.id}, salt=SALT)


def courier_from_request(request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        data = signing.loads(auth[7:], salt=SALT, max_age=TOKEN_MAX_AGE)
    except signing.BadSignature:
        return None
    return Courier.objects.filter(id=data.get("cid"), is_active=True).first()


def _fmt(amount):
    return f"{amount:,.0f}".replace(",", " ")


def _serialize(d: Delivery):
    o = d.order
    remaining = None
    if d.acceptance_deadline and d.status == Delivery.Status.ASSIGNED:
        remaining = int((d.acceptance_deadline - timezone.now()).total_seconds())
    return {
        "id": d.id,
        "status": d.status,
        "status_display": d.get_status_display(),
        "code": d.delivery_code if d.status == Delivery.Status.ACCEPTED else "",
        "acceptance_deadline": d.acceptance_deadline.isoformat() if d.acceptance_deadline else None,
        "remaining_seconds": remaining,
        "is_overdue": d.is_overdue,
        "zone": {"name": d.zone.name, "fee": str(d.zone.fee)} if d.zone else None,
        "order": {
            "reference": o.reference,
            "customer_name": o.customer_name,
            "phone": o.phone,
            "address": o.address,
            "note": o.note,
            "total": str(o.total),
            "delivery_fee": str(o.delivery_fee),
            "grand_total": str(o.grand_total),
            "items": [
                {
                    "product_name": it.product_name,
                    "quantity": it.quantity,
                    "size": it.size,
                    "line_total": str(it.line_total),
                }
                for it in o.items.all()
            ],
        },
    }


@api_view(["POST"])
def courier_login(request):
    phone = (request.data.get("phone") or "").strip()
    norm = phone.replace(" ", "").lstrip("+")
    courier = (
        Courier.objects.filter(is_active=True)
        .filter(Q(phone=phone) | Q(phone=norm) | Q(phone="237" + norm) | Q(phone=norm.lstrip("237")))
        .first()
    )
    if not courier:
        return Response(
            {"detail": "Numéro non reconnu. Contactez Tchokos pour être enregistré."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(
        {
            "token": make_token(courier),
            "courier": {"id": courier.id, "name": courier.name, "phone": courier.phone},
        }
    )


@api_view(["GET"])
def courier_deliveries(request):
    courier = courier_from_request(request)
    if not courier:
        return Response({"detail": "Non autorisé."}, status=status.HTTP_401_UNAUTHORIZED)

    qs = (
        Delivery.objects.filter(courier=courier)
        .select_related("order", "zone")
        .prefetch_related("order__items")
    )
    # Expire à la volée les courses dont la fenêtre de 4h est dépassée
    for d in qs:
        if d.is_overdue:
            d.expire()

    return Response(
        {
            "courier": {"name": courier.name, "phone": courier.phone},
            "deliveries": [_serialize(d) for d in qs],
        }
    )


@api_view(["POST"])
def courier_accept(request, pk):
    courier = courier_from_request(request)
    if not courier:
        return Response({"detail": "Non autorisé."}, status=status.HTTP_401_UNAUTHORIZED)
    d = Delivery.objects.filter(pk=pk, courier=courier).first()
    if not d:
        return Response({"detail": "Course introuvable."}, status=status.HTTP_404_NOT_FOUND)
    try:
        code = d.accept()
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"code": code, "status": d.status})


@api_view(["POST"])
def courier_complete(request, pk):
    courier = courier_from_request(request)
    if not courier:
        return Response({"detail": "Non autorisé."}, status=status.HTTP_401_UNAUTHORIZED)
    d = Delivery.objects.filter(pk=pk, courier=courier).first()
    if not d:
        return Response({"detail": "Course introuvable."}, status=status.HTTP_404_NOT_FOUND)
    code = (request.data.get("code") or "").strip()
    if d.complete_with_code(code):
        return Response({"status": d.status})
    return Response(
        {"detail": "Code de livraison invalide."}, status=status.HTTP_400_BAD_REQUEST
    )
