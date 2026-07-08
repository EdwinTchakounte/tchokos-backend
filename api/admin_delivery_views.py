"""Back-office ADMIN — livraisons, zones/tarifs, décaissements livreurs.

Complète le dashboard (commandes/paiements) avec le pilotage de la livraison :
suivi et assignation des courses, édition des tarifs par zone, et règlement
des décaissements livreur↔plateforme. Réservé aux admins (`IsAdminRole`).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db.models import Q, Sum
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsAdminRole
from delivery.models import Courier, Delivery, DeliveryZone, Settlement


def _int_or_400(value, field):
    try:
        n = int(float(value))
        if n < 0:
            raise ValueError
        return n, None
    except (TypeError, ValueError, InvalidOperation):
        return None, Response({"detail": f"{field} invalide."}, status=status.HTTP_400_BAD_REQUEST)


def _float_or_none(value):
    """Convertit une coordonnée en float, ou None si vide/invalide."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Livraisons
# ---------------------------------------------------------------------------


def _delivery_dict(d: Delivery) -> dict:
    return {
        "id": d.id,
        "order_reference": d.order.reference,
        "customer_name": d.order.customer_name,
        "phone": d.order.phone,
        "city": d.order.city,
        "grand_total": str(d.order.grand_total),
        "status": d.status,
        "status_display": d.get_status_display(),
        "courier": {"id": d.courier_id, "name": d.courier.name} if d.courier_id else None,
        "zone": {"id": d.zone_id, "name": d.zone.name, "fee": str(d.zone.fee)} if d.zone_id else None,
        "acceptance_deadline": d.acceptance_deadline.isoformat() if d.acceptance_deadline else None,
        "is_overdue": d.is_overdue,
        "flagged_for_review": d.flagged_for_review,
        "created_at": d.created_at.isoformat(),
    }


@api_view(["GET"])
@permission_classes([IsAdminRole])
def admin_deliveries(request):
    qs = Delivery.objects.select_related("order", "courier", "zone").order_by("-created_at")
    statut = request.query_params.get("status")
    if statut:
        qs = qs.filter(status=statut)
    if request.query_params.get("flagged") in ("1", "true"):
        qs = qs.filter(flagged_for_review=True)
    q = (request.query_params.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(order__reference__icontains=q)
            | Q(order__customer_name__icontains=q)
            | Q(order__phone__icontains=q)
        )
    rows = list(qs[:200])
    return Response({"count": len(rows), "results": [_delivery_dict(d) for d in rows]})


@api_view(["GET", "POST"])
@permission_classes([IsAdminRole])
def admin_couriers(request):
    if request.method == "POST":
        return _create_courier(request)
    couriers = Courier.objects.prefetch_related("zones").select_related("user").all()
    return Response([_courier_dict(c) for c in couriers])


def _courier_dict(c: Courier) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "phone": c.phone,
        "email": c.user.email if c.user_id else "",
        "city": c.city,
        "vehicle": c.vehicle,
        "is_active": c.is_active,
        "is_available": c.is_available,
        "latitude": c.latitude,
        "longitude": c.longitude,
        "zone_ids": [z.id for z in c.zones.all()],
        "zones": [z.name for z in c.zones.all()],
    }


def _create_courier(request):
    name = (request.data.get("name") or "").strip()
    phone = (request.data.get("phone") or "").strip()
    email = (request.data.get("email") or "").strip().lower()
    if not name or not phone:
        return Response({"detail": "Nom et téléphone obligatoires."}, status=status.HTTP_400_BAD_REQUEST)
    if not email:
        return Response({"detail": "Email obligatoire (compte livreur)."}, status=status.HTTP_400_BAD_REQUEST)
    if Courier.objects.filter(phone=phone).exists():
        return Response({"detail": "Un livreur avec ce téléphone existe déjà."}, status=status.HTTP_400_BAD_REQUEST)

    from accounts.emails import send_account_invite
    from accounts.models import User

    user = User.objects.filter(email__iexact=email).first()
    created_user = False
    if user is None:
        user = User(email=email, full_name=name, role=User.Role.COURIER)
        if not User.objects.filter(phone=phone).exists():
            user.phone = phone
        user.set_unusable_password()
        user.save()
        created_user = True
    elif user.role != User.Role.COURIER:
        user.role = User.Role.COURIER
        user.save(update_fields=["role"])

    courier = Courier.objects.create(
        user=user,
        name=name,
        phone=phone,
        city=(request.data.get("city") or "Douala").strip(),
        vehicle=(request.data.get("vehicle") or "Moto").strip(),
        is_active=bool(request.data.get("is_active", True)),
        is_available=bool(request.data.get("is_available", True)),
        latitude=_float_or_none(request.data.get("latitude")),
        longitude=_float_or_none(request.data.get("longitude")),
    )
    zone_ids = request.data.get("zone_ids") or []
    if zone_ids:
        courier.zones.set(DeliveryZone.objects.filter(id__in=zone_ids))
    # Email d'activation (définir le mot de passe) si compte neuf.
    if created_user or not user.has_usable_password():
        send_account_invite(user)
    return Response(_courier_dict(courier), status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAdminRole])
def admin_courier_detail(request, pk):
    c = Courier.objects.filter(pk=pk).first()
    if not c:
        return Response({"detail": "Livreur introuvable."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        # Désactive (conserve l'historique) s'il a déjà des courses, sinon supprime.
        if Delivery.objects.filter(courier=c).exists():
            c.is_active = False
            c.is_available = False
            c.save(update_fields=["is_active", "is_available"])
            return Response({"detail": "Livreur désactivé (historique conservé)."})
        c.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    d = request.data
    for f in ("name", "city", "vehicle"):
        if f in d:
            setattr(c, f, (d.get(f) or "").strip())
    if "phone" in d:
        phone = (d.get("phone") or "").strip()
        if phone and Courier.objects.filter(phone=phone).exclude(pk=c.pk).exists():
            return Response({"detail": "Téléphone déjà utilisé."}, status=status.HTTP_400_BAD_REQUEST)
        c.phone = phone
    for b in ("is_active", "is_available"):
        if b in d:
            setattr(c, b, bool(d[b]))
    if "latitude" in d:
        c.latitude = _float_or_none(d.get("latitude"))
    if "longitude" in d:
        c.longitude = _float_or_none(d.get("longitude"))
    c.save()
    if "zone_ids" in d:
        c.zones.set(DeliveryZone.objects.filter(id__in=(d.get("zone_ids") or [])))
    return Response(_courier_dict(c))


@api_view(["POST"])
@permission_classes([IsAdminRole])
def admin_delivery_assign(request, pk):
    d = Delivery.objects.filter(pk=pk).first()
    if not d:
        return Response({"detail": "Livraison introuvable."}, status=status.HTTP_404_NOT_FOUND)
    if d.status in (Delivery.Status.COMPLETED, Delivery.Status.CANCELLED):
        return Response(
            {"detail": "Course déjà finalisée — assignation impossible."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    courier = Courier.objects.filter(pk=request.data.get("courier_id"), is_active=True).first()
    if not courier:
        return Response({"detail": "Livreur introuvable ou inactif."}, status=status.HTTP_400_BAD_REQUEST)
    d.assign(courier)  # relance la fenêtre de 4h
    return Response(_delivery_dict(d))


# ---------------------------------------------------------------------------
# Zones & tarifs
# ---------------------------------------------------------------------------


def _zone_dict(z: DeliveryZone) -> dict:
    return {
        "id": z.id,
        "name": z.name,
        "city": z.city,
        "fee": str(z.fee),
        "eta_minutes": z.eta_minutes,
        "is_active": z.is_active,
        "order": z.order,
        "latitude": z.latitude,
        "longitude": z.longitude,
    }


@api_view(["GET", "POST"])
@permission_classes([IsAdminRole])
def admin_delivery_zones(request):
    if request.method == "POST":
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"detail": "Nom de zone obligatoire."}, status=status.HTTP_400_BAD_REQUEST)
        fee, err = _int_or_400(request.data.get("fee", 0), "Tarif")
        if err:
            return err
        eta, err = _int_or_400(request.data.get("eta_minutes", 60), "Délai")
        if err:
            return err
        z = DeliveryZone.objects.create(
            name=name,
            city=(request.data.get("city") or "Douala").strip(),
            fee=fee,
            eta_minutes=eta,
            is_active=bool(request.data.get("is_active", True)),
            order=int(request.data.get("order") or 0),
            latitude=_float_or_none(request.data.get("latitude")),
            longitude=_float_or_none(request.data.get("longitude")),
        )
        return Response(_zone_dict(z), status=status.HTTP_201_CREATED)

    zones = DeliveryZone.objects.all()
    return Response([_zone_dict(z) for z in zones])


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAdminRole])
def admin_delivery_zone_detail(request, pk):
    z = DeliveryZone.objects.filter(pk=pk).first()
    if not z:
        return Response({"detail": "Zone introuvable."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        if z.deliveries.exists():
            # On préserve l'historique : on désactive plutôt que supprimer.
            z.is_active = False
            z.save(update_fields=["is_active"])
            return Response(_zone_dict(z))
        z.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    d = request.data
    if "name" in d:
        name = (d.get("name") or "").strip()
        if not name:
            return Response({"detail": "Nom obligatoire."}, status=status.HTTP_400_BAD_REQUEST)
        z.name = name
    if "city" in d:
        z.city = (d.get("city") or "Douala").strip()
    if "fee" in d:
        fee, err = _int_or_400(d["fee"], "Tarif")
        if err:
            return err
        z.fee = fee
    if "eta_minutes" in d:
        eta, err = _int_or_400(d["eta_minutes"], "Délai")
        if err:
            return err
        z.eta_minutes = eta
    if "is_active" in d:
        z.is_active = bool(d["is_active"]) if isinstance(d["is_active"], bool) else str(d["is_active"]).lower() in ("1", "true", "on")
    if "order" in d:
        z.order = int(d.get("order") or 0)
    if "latitude" in d:
        z.latitude = _float_or_none(d.get("latitude"))
    if "longitude" in d:
        z.longitude = _float_or_none(d.get("longitude"))
    z.save()
    return Response(_zone_dict(z))


# ---------------------------------------------------------------------------
# Décaissements livreur ↔ plateforme
# ---------------------------------------------------------------------------


def _settlement_dict(s: Settlement) -> dict:
    return {
        "id": s.id,
        "order_reference": s.delivery.order.reference,
        "courier": s.courier.name if s.courier_id else "—",
        "direction": s.direction,
        "direction_display": s.get_direction_display(),
        "is_cod": s.is_cod,
        "collected": str(s.collected),
        "courier_fee": str(s.courier_fee),
        "amount": str(s.amount),
        "status": s.status,
        "status_display": s.get_status_display(),
        "settled_at": s.settled_at.isoformat() if s.settled_at else None,
        "note": s.note,
        "created_at": s.created_at.isoformat(),
    }


@api_view(["GET"])
@permission_classes([IsAdminRole])
def admin_settlements(request):
    # Auto-réparation : génère les décaissements manquants pour les courses déjà
    # livrées (idempotent) — utile pour l'historique antérieur à cette fonction.
    completed_without = (
        Delivery.objects.filter(status=Delivery.Status.COMPLETED, settlement__isnull=True)
        .select_related("order")
    )
    for d in completed_without:
        Settlement.ensure_for_delivery(d)

    qs = Settlement.objects.select_related("delivery__order", "courier").order_by("-created_at")
    statut = request.query_params.get("status")
    if statut:
        qs = qs.filter(status=statut)
    direction = request.query_params.get("direction")
    if direction:
        qs = qs.filter(direction=direction)

    rows = list(qs[:200])
    # Résumé : soldes en attente par direction.
    pending = Settlement.objects.filter(status=Settlement.Status.PENDING)
    owed_to_platform = pending.filter(
        direction=Settlement.Direction.COURIER_TO_PLATFORM
    ).aggregate(s=Sum("amount"))["s"] or 0
    owed_to_couriers = pending.filter(
        direction=Settlement.Direction.PLATFORM_TO_COURIER
    ).aggregate(s=Sum("amount"))["s"] or 0

    return Response(
        {
            "count": len(rows),
            "summary": {
                "owed_to_platform": str(int(owed_to_platform)),
                "owed_to_couriers": str(int(owed_to_couriers)),
                "pending_count": pending.count(),
            },
            "results": [_settlement_dict(s) for s in rows],
        }
    )


@api_view(["POST"])
@permission_classes([IsAdminRole])
def admin_settlement_settle(request, pk):
    s = Settlement.objects.filter(pk=pk).first()
    if not s:
        return Response({"detail": "Décaissement introuvable."}, status=status.HTTP_404_NOT_FOUND)
    if s.status == Settlement.Status.SETTLED:
        return Response(_settlement_dict(s))
    s.mark_settled(note=(request.data.get("note") or "").strip())
    return Response(_settlement_dict(s))
