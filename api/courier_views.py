"""API de l'espace livreur.

Authentification désormais unifiée via ``accounts`` : le livreur a un compte
``User`` (email + mot de passe, ou OTP téléphone) et un profil ``Courier`` lié.
Les endpoints protégés utilisent le JWT (``request.user``) + la permission
``IsCourier``. L'inscription crée le User et le profil livreur.
"""
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.permissions import IsCourier
from accounts.serializers import UserSerializer
from delivery.models import Courier, Delivery, DeliveryZone

logger = logging.getLogger(__name__)
User = get_user_model()


def _norm(phone: str) -> str:
    return (phone or "").replace(" ", "").lstrip("+")


def _stats(courier: Courier):
    d = Delivery.objects.filter(courier=courier)
    completed = d.filter(status=Delivery.Status.COMPLETED)
    earnings = completed.aggregate(s=Sum("order__delivery_fee"))["s"] or 0
    return {
        "assigned": d.filter(status=Delivery.Status.ASSIGNED).count(),
        "in_progress": d.filter(status=Delivery.Status.ACCEPTED).count(),
        "completed": completed.count(),
        "to_review": d.filter(flagged_for_review=True, reviewed=False).count(),
        "earnings": str(earnings),
        "deliveries_total": d.count(),
    }


def _serialize_delivery(dv: Delivery):
    o = dv.order
    remaining = None
    if dv.acceptance_deadline and dv.status == Delivery.Status.ASSIGNED:
        remaining = int((dv.acceptance_deadline - timezone.now()).total_seconds())
    return {
        "id": dv.id,
        "status": dv.status,
        "status_display": dv.get_status_display(),
        # Le code n'est JAMAIS exposé au livreur : il est envoyé au client, qui
        # le communique au livreur à la réception. On indique juste s'il est parti.
        "code_sent": bool(dv.delivery_code) and dv.status == Delivery.Status.ACCEPTED,
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


def _courier_of(request):
    """Profil livreur de l'utilisateur connecté (None sinon)."""
    return getattr(request.user, "courier_profile", None)


# ----------------------------- public / inscription -----------------------------

@api_view(["GET"])
@permission_classes([AllowAny])
def courier_zones(request):
    zones = DeliveryZone.objects.filter(is_active=True)
    return Response([{"id": z.id, "name": z.name, "fee": str(z.fee)} for z in zones])


@api_view(["POST"])
@permission_classes([AllowAny])
def courier_register(request):
    """Inscription livreur : crée le compte User (rôle livreur) + le profil Courier."""
    name = (request.data.get("name") or "").strip()
    email = (request.data.get("email") or "").strip().lower()
    password = request.data.get("password") or ""
    phone = _norm(request.data.get("phone") or "")
    vehicle = (request.data.get("vehicle") or "Moto").strip()
    zone_ids = request.data.get("zone_ids") or []

    if not name or not email or not password or not phone:
        return Response({"detail": "Nom, email, téléphone et mot de passe obligatoires."}, status=400)
    if User.objects.filter(email__iexact=email).exists():
        return Response({"detail": "Cet email a déjà un compte. Connectez-vous."}, status=409)
    if User.objects.filter(phone=phone).exists():
        return Response({"detail": "Ce numéro est déjà utilisé."}, status=409)
    try:
        validate_password(password)
    except ValidationError as exc:
        return Response({"detail": " ".join(exc.messages)}, status=400)

    with transaction.atomic():
        user = User.objects.create_user(
            email=email, password=password, full_name=name,
            phone=phone, role=User.Role.COURIER,
        )
        courier = Courier.objects.create(
            user=user, name=name, phone=phone, vehicle=vehicle,
            is_active=True, is_available=True,
        )
        if zone_ids:
            courier.zones.set(DeliveryZone.objects.filter(id__in=zone_ids))

    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
            "profile": _profile(courier),
        },
        status=status.HTTP_201_CREATED,
    )


# ----------------------------- espace (JWT + IsCourier) -----------------------------

@api_view(["GET"])
@permission_classes([IsCourier])
def courier_me(request):
    courier = _courier_of(request)
    return Response({"profile": _profile(courier), "stats": _stats(courier)})


@api_view(["POST"])
@permission_classes([IsCourier])
def courier_set_availability(request):
    courier = _courier_of(request)
    courier.is_available = bool(request.data.get("is_available"))
    courier.save(update_fields=["is_available"])
    return Response({"is_available": courier.is_available})


@api_view(["GET"])
@permission_classes([IsCourier])
def courier_deliveries(request):
    courier = _courier_of(request)
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
@permission_classes([IsCourier])
def courier_accept(request, pk):
    courier = _courier_of(request)
    dv = Delivery.objects.filter(pk=pk, courier=courier).first()
    if not dv:
        return Response({"detail": "Course introuvable."}, status=status.HTTP_404_NOT_FOUND)
    try:
        dv.accept()
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    # Le code part au CLIENT (email; WhatsApp si configuré) — jamais au livreur.
    from delivery.notifications import send_delivery_code

    notified = send_delivery_code(dv)
    return Response({"status": dv.status, "notified": notified})


@api_view(["POST"])
@permission_classes([IsCourier])
def courier_complete(request, pk):
    courier = _courier_of(request)
    dv = Delivery.objects.filter(pk=pk, courier=courier).first()
    if not dv:
        return Response({"detail": "Course introuvable."}, status=status.HTTP_404_NOT_FOUND)
    code = (request.data.get("code") or "").strip()
    if dv.complete_with_code(code):
        # Génère le décaissement (règlement livreur↔plateforme) — idempotent.
        try:
            from delivery.models import Settlement

            Settlement.ensure_for_delivery(dv)
        except Exception:  # noqa: BLE001 — ne bloque pas la validation de course
            logger.warning("Décaissement non créé pour %s", dv.order.reference, exc_info=True)
        return Response({"status": dv.status})
    return Response({"detail": "Code de livraison invalide."}, status=status.HTTP_400_BAD_REQUEST)
