"""Cœur métier des paiements — init, webhook idempotent, hooks.

La vue webhook reste mince : elle authentifie, verrouille la ligne Payment,
pose ``statut=valide`` et délègue ici. `handle_webhook_event` est atomique et
idempotent : un même événement rejoué est un no-op. Le hook métier
(`_hook_order_paid`) doit lui aussi être **idempotent** et **ne jamais lever**.
"""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Payment
from .providers import get_provider


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Init payin
# ---------------------------------------------------------------------------


def init_payin_for_payment(
    payment: Payment, *, phone: str, network: str = ""
) -> tuple[str | None, str, dict]:
    """Pousse une demande de payin au provider configuré.

    Met à jour ``reference_externe`` et ``gateway_initiated_at`` sur le Payment
    en place — le caller doit persister (``save``).
    Retourne ``(payment_url, provider_reference, provider_raw)``.
    """
    provider = get_provider(payment.provider_code or "tara")
    result = provider.init_payin(payment, phone=phone, network=network)
    payment.reference_externe = result.provider_reference
    payment.gateway_initiated_at = timezone.now()
    return result.payment_url, result.provider_reference, result.raw or {}


def start_order_payment(order, *, phone: str, network: str = "") -> tuple[Payment, str | None, dict]:
    """Crée un Payment ``en_attente`` pour une commande et initie le payin Tara.

    Anti double-tap : réutilise un Payment ``en_attente`` récent (< 2 min) de la
    même commande plutôt que de déclencher un second STK Push. Retourne
    ``(payment, payment_url, provider_raw)``. Le Payment est persisté.
    """
    recent_cutoff = timezone.now() - timedelta(minutes=2)
    existing = (
        Payment.objects.filter(
            order=order,
            statut=Payment.Statut.EN_ATTENTE,
            source=Payment.Source.MOBILE_MONEY,
            created_at__gte=recent_cutoff,
        )
        .order_by("-created_at")
        .first()
    )
    if existing is not None:
        return existing, None, {"dedup": True}

    payment = Payment.objects.create(
        order=order,
        user=order.user,
        montant=order.grand_total,
        source=Payment.Source.MOBILE_MONEY,
        statut=Payment.Statut.EN_ATTENTE,
        provider_code="tara",
        phone=phone or order.phone,
        network=network,
    )
    payment_url, _ref, raw = init_payin_for_payment(
        payment, phone=phone or order.phone, network=network
    )
    payment.save(update_fields=["reference_externe", "gateway_initiated_at", "updated_at"])
    return payment, payment_url, raw


# ---------------------------------------------------------------------------
# Webhook idempotent
# ---------------------------------------------------------------------------


@transaction.atomic
def handle_webhook_event(
    payment_idempotency_key: str | uuid.UUID,
    new_status: str,
    *,
    provider_reference: str = "",
    raw_payload: dict | None = None,
) -> Payment:
    """Applique un événement webhook vérifié au Payment correspondant.

    Idempotent : rejouer le même événement est un no-op. Lève
    ``Payment.DoesNotExist`` si la clé est inconnue (la vue renvoie alors 404
    pour que Tara arrête de relancer).
    """
    raw_payload = raw_payload or {}
    payment = None
    match_strategy = None

    # Stratégie 1 — UUID idempotency_key direct (cas nominal : Tara renvoie
    # notre productId).
    try:
        uuid.UUID(str(payment_idempotency_key))
        payment = Payment.objects.select_for_update().get(
            idempotency_key=payment_idempotency_key
        )
        match_strategy = "uuid"
    except (ValueError, TypeError, Payment.DoesNotExist):
        payment = None

    # Stratégie 2 — reference_externe == clé ou provider_reference.
    if payment is None:
        candidates = Payment.objects.select_for_update().filter(
            reference_externe=str(payment_idempotency_key)
        )
        if not candidates.exists() and provider_reference:
            candidates = Payment.objects.select_for_update().filter(
                reference_externe=str(provider_reference)
            )
        if candidates.exists():
            payment = (
                candidates.filter(statut=Payment.Statut.EN_ATTENTE)
                .order_by("-created_at")
                .first()
                or candidates.order_by("-created_at").first()
            )
            if payment is not None:
                match_strategy = "reference_externe"

    # Stratégie 3 — repli par téléphone : Payment EN_ATTENTE le plus récent
    # (< 30 min) dont le numéro payeur correspond. Dernier recours quand Tara
    # ne renvoie ni notre productId ni une référence déjà stockée.
    if payment is None and raw_payload.get("phoneNumber"):
        phone_raw = str(raw_payload["phoneNumber"])
        digits_only = "".join(c for c in phone_raw if c.isdigit())
        local_9 = digits_only[-9:] if len(digits_only) >= 9 else digits_only
        recent_cutoff = timezone.now() - timedelta(minutes=30)
        payment = (
            Payment.objects.select_for_update()
            .filter(
                statut=Payment.Statut.EN_ATTENTE,
                created_at__gte=recent_cutoff,
                phone__icontains=local_9,
            )
            .order_by("-created_at")
            .first()
        )
        if payment is not None:
            match_strategy = "phone_recent"

    if payment is None:
        logger.warning(
            "[TARA] webhook MATCH FAILED — key=%r ref=%r phone=%r status=%r",
            payment_idempotency_key,
            provider_reference,
            raw_payload.get("phoneNumber"),
            new_status,
        )
        raise Payment.DoesNotExist()

    logger.info(
        "[TARA] webhook MATCH OK — strategy=%s payment_id=%s %s → %s",
        match_strategy,
        payment.id,
        payment.statut,
        new_status,
    )

    # On mémorise le paymentId Tara comme reference_externe (aide un rejeu
    # ultérieur à matcher direct par stratégie 2).
    if provider_reference and payment.reference_externe != provider_reference:
        payment.reference_externe = provider_reference
        payment.save(update_fields=["reference_externe", "updated_at"])

    # États terminaux non ré-évalués.
    if payment.statut == Payment.Statut.VALIDE:
        return payment
    if payment.statut == Payment.Statut.REJETE and new_status != "valide":
        return payment

    if new_status == "valide":
        return _confirm(payment, provider_reference=provider_reference, raw=raw_payload)
    if new_status == "rejete":
        return _reject(payment, raw=raw_payload)
    # "en_attente" — le provider dit « toujours en cours », rien à changer.
    return payment


# ---------------------------------------------------------------------------
# Confirmation / rejet
# ---------------------------------------------------------------------------


def _confirm(payment: Payment, *, provider_reference: str, raw: dict) -> Payment:
    payment.statut = Payment.Statut.VALIDE
    payment.date_validation = timezone.now()
    if provider_reference:
        payment.reference_externe = provider_reference
    payment.save(
        update_fields=["statut", "date_validation", "reference_externe", "updated_at"]
    )
    _hook_order_paid(payment, raw)
    return payment


def _reject(payment: Payment, *, raw: dict) -> Payment:
    payment.statut = Payment.Statut.REJETE
    payment.motif_rejet = (raw.get("message") or raw.get("reason") or "Rejeté par le provider")[:500]
    payment.save(update_fields=["statut", "motif_rejet", "updated_at"])
    return payment


# ---------------------------------------------------------------------------
# Hook métier — commande payée
# ---------------------------------------------------------------------------


def _hook_order_paid(payment: Payment, _raw: dict) -> None:
    """Effet de bord d'un paiement validé : la commande passe à PAID.

    Idempotent (garde sur ``order.status``) et **ne lève jamais** — toute
    erreur secondaire (Sendo) est loggée sans casser le webhook.
    """
    from orders.models import Order

    order = payment.order
    if order.status == Order.Status.PAID:
        return  # déjà traité (rejeu webhook)

    # Ne pas rétrograder une commande déjà livrée.
    if order.status != Order.Status.DELIVERED:
        order.status = Order.Status.PAID
        order.save(update_fields=["status", "updated_at"])

    logger.info(
        "[PAYMENTS] commande %s marquée PAYÉE (payment #%s, %s FCFA)",
        order.reference,
        payment.id,
        payment.montant,
    )

    # Pousse best-effort vers Sendo si la commande doit être livrée et n'a pas
    # encore de colis. Ne casse jamais le webhook.
    if not order.sendo_shipment_id and order.delivery_fee:
        try:
            from integrations import sendo

            shipment = sendo.create_shipment(order)
            if shipment:
                order.sendo_shipment_id = shipment.get("id", "")
                order.sendo_tracking_token = shipment.get("tracking_token", "")
                order.sendo_status = shipment.get("status", "")
                order.save(
                    update_fields=[
                        "sendo_shipment_id",
                        "sendo_tracking_token",
                        "sendo_status",
                        "updated_at",
                    ]
                )
        except Exception:  # noqa: BLE001 — best-effort
            logger.warning(
                "[PAYMENTS] push Sendo après paiement a échoué (commande %s)",
                order.reference,
                exc_info=True,
            )
