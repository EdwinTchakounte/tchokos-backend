"""API de l'espace livreur — module de connexion complet (OTP + inscription).

Auth par OTP (code à 6 chiffres) « envoyé » au téléphone. En démo, le code est
renvoyé dans la réponse (champ ``demo_code``) et loggé ; en production il serait
envoyé par SMS/WhatsApp (Brevo / passerelle SMS).
"""
import logging
import secrets
from datetime import timedelta

from django.core import signing
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from delivery.models import Courier, Delivery, DeliveryZone

logger = logging.getLogger(__name__)

SALT = "tchokos-courier-auth"
TOKEN_MAX_AGE = 60 * 60 * 24 * 30
OTP_TTL_MIN = 5


# ----------------------------- helpers -----------------------------

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


def _norm(phone: str) -> str:
    return (phone or "").replace(" ", "").lstrip("+")


def _find_courier(phone: str):
    n = _norm(phone)
    return (
        Courier.objects.filter(is_active=True)
        .filter(Q(phone=phone) | Q(phone=n) | Q(phone="237" + n))
        .first()
    )


def _stats(courier: Courier):
    d = Delivery.objects.filter(courier=courier)
    completed = d.filter(status=Delivery.Status.COMPLETED)
    earnings = (
        completed.aggregate(s=Sum("order__delivery_fee"))["s"] or 0
    )
    return {
        "assigned": d.filter(status=Delivery.Status.ASSIGNED).count(),
        "in_progress": d.filter(status=Delivery.Status.ACCEPTED).count(),
        "completed": completed.count(),
        "to_review": d.filter(flagged_for_review=True, reviewed=False).count(),
        "earnings": str(earnings),
        "deliveries_total": d.count(),
    }


def _fmt(amount):
    return f"{amount:,.0f}".replace(",", " ")


def _serialize_delivery(dv: Delivery):
    o = dv.order
    remaining = None
    if dv.acceptance_deadline and dv.status == Delivery.Status.ASSIGNED:
        remaining = int((dv.acceptance_deadline - timezone.now()).total_seconds())
    return {
        "id": dv.id,
        "status": dv.status,
        "status_display": dv.get_status_display(),
        "code": dv.delivery_code if dv.status == Delivery.Status.ACCEPTED else "",
        "acceptance_deadline": dv.acceptance_deadline.isoformat() if dv.acceptance_deadline else None,
        "remaining_seconds": remaining,
        "is_overdue": dv.is_overdue,
        "zone": {"name": dv.zone.name, "fee": str(dv.zone.fee)} if dv.zone else None,
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


def _profile(courier: Courier):
    return {
        "id": courier.id,
        "name": courier.name,
        "phone": courier.phone,
        "city": courier.city,
        "vehicle": courier.vehicle,
        "is_available": courier.is_available,
        "zones": [z.name for z in courier.zones.all()],
    }


# ----------------------------- auth (OTP) -----------------------------

@api_view(["GET"])
def courier_zones(request):
    zones = DeliveryZone.objects.filter(is_active=True)
    return Response([{"id": z.id, "name": z.name, "fee": str(z.fee)} for z in zones])


@api_view(["POST"])
def courier_register(request):
    name = (request.data.get("name") or "").strip()
    phone = (request.data.get("phone") or "").strip()
    vehicle = (request.data.get("vehicle") or "Moto").strip()
    zone_ids = request.data.get("zone_ids") or []
    if not name or not phone:
        return Response({"detail": "Nom et téléphone obligatoires."}, status=400)
    if _find_courier(phone) or Courier.objects.filter(phone=_norm(phone)).exists():
        return Response({"detail": "Ce numéro est déjà enregistré. Connectez-vous."}, status=409)
    courier = Courier.objects.create(
        name=name, phone=_norm(phone), vehicle=vehicle, is_active=True, is_available=True
    )
    if zone_ids:
        courier.zones.set(DeliveryZone.objects.filter(id__in=zone_ids))
    return Response({"detail": "Compte créé. Connectez-vous avec votre numéro."}, status=201)


@api_view(["POST"])
def courier_request_otp(request):
    phone = (request.data.get("phone") or "").strip()
    courier = _find_courier(phone)
    if not courier:
        return Response(
            {"detail": "Numéro non reconnu. Créez un compte livreur."},
            status=status.HTTP_404_NOT_FOUND,
        )
    code = f"{secrets.randbelow(1_000_000):06d}"
    courier.otp_code = code
    courier.otp_expires_at = timezone.now() + timedelta(minutes=OTP_TTL_MIN)
    courier.save(update_fields=["otp_code", "otp_expires_at"])
    # En prod : envoyer `code` par SMS/WhatsApp. En démo on le renvoie.
    logger.info("[Courier OTP] %s → %s", courier.phone, code)
    return Response({"sent": True, "demo_code": code, "ttl_minutes": OTP_TTL_MIN})


@api_view(["POST"])
def courier_verify_otp(request):
    phone = (request.data.get("phone") or "").strip()
    code = (request.data.get("code") or "").strip()
    courier = _find_courier(phone)
    if not courier or not courier.otp_code:
        return Response({"detail": "Demandez d'abord un code."}, status=400)
    if not courier.otp_expires_at or timezone.now() > courier.otp_expires_at:
        return Response({"detail": "Code expiré. Demandez-en un nouveau."}, status=400)
    if code != courier.otp_code:
        return Response({"detail": "Code incorrect."}, status=400)
    courier.otp_code = ""
    courier.otp_expires_at = None
    courier.save(update_fields=["otp_code", "otp_expires_at"])
    return Response({"token": make_token(courier), "courier": _profile(courier)})


# ----------------------------- espace -----------------------------

@api_view(["GET"])
def courier_me(request):
    courier = courier_from_request(request)
    if not courier:
        return Response({"detail": "Non autorisé."}, status=status.HTTP_401_UNAUTHORIZED)
    return Response({"profile": _profile(courier), "stats": _stats(courier)})


@api_view(["POST"])
def courier_set_availability(request):
    courier = courier_from_request(request)
    if not courier:
        return Response({"detail": "Non autorisé."}, status=status.HTTP_401_UNAUTHORIZED)
    courier.is_available = bool(request.data.get("is_available"))
    courier.save(update_fields=["is_available"])
    return Response({"is_available": courier.is_available})


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
    for dv in qs:
        if dv.is_overdue:
            dv.expire()
    return Response({
        "profile": _profile(courier),
        "stats": _stats(courier),
        "deliveries": [_serialize_delivery(dv) for dv in qs],
    })


@api_view(["POST"])
def courier_accept(request, pk):
    courier = courier_from_request(request)
    if not courier:
        return Response({"detail": "Non autorisé."}, status=status.HTTP_401_UNAUTHORIZED)
    dv = Delivery.objects.filter(pk=pk, courier=courier).first()
    if not dv:
        return Response({"detail": "Course introuvable."}, status=status.HTTP_404_NOT_FOUND)
    try:
        code = dv.accept()
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"code": code, "status": dv.status})


@api_view(["POST"])
def courier_complete(request, pk):
    courier = courier_from_request(request)
    if not courier:
        return Response({"detail": "Non autorisé."}, status=status.HTTP_401_UNAUTHORIZED)
    dv = Delivery.objects.filter(pk=pk, courier=courier).first()
    if not dv:
        return Response({"detail": "Course introuvable."}, status=status.HTTP_404_NOT_FOUND)
    code = (request.data.get("code") or "").strip()
    if dv.complete_with_code(code):
        return Response({"status": dv.status})
    return Response({"detail": "Code de livraison invalide."}, status=status.HTTP_400_BAD_REQUEST)
