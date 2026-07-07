"""Tâches d'arrière-plan des paiements — filet de réconciliation Tara.

Fonctions simples, appelables via ``manage.py reconcile_payments`` ou un cron
(django-q2 / Celery / crontab système). Repêche les Payment ``en_attente`` que
Tara n'a jamais confirmés par webhook, interroge ``check_status`` et
valide/rejette. Timeout dur à 24h.
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Payment
from .providers import get_provider
from .providers.base import ProviderError
from .services import handle_webhook_event


logger = logging.getLogger(__name__)

# Délai avant de considérer le silence du provider comme suspect (poll actif).
RECONCILE_AFTER = timedelta(minutes=2)
# Délai avant d'abandonner un paiement en attente.
GIVE_UP_AFTER = timedelta(hours=24)

# Tara throttle ~3 req/min : on espace les appels.
INTER_CALL_DELAY = 2.0
RATE_LIMIT_RETRY_DELAY = 25.0


def reconcile_pending_payments(*, batch_size: int = 100) -> dict:
    """Pour chaque Payment ``en_attente`` dépassant ``RECONCILE_AFTER``,
    interroge le provider et applique le statut. Retourne un résumé.
    """
    now = timezone.now()
    stale_threshold = now - RECONCILE_AFTER
    timeout_threshold = now - GIVE_UP_AFTER

    base_qs = (
        Payment.objects.filter(
            statut=Payment.Statut.EN_ATTENTE,
            source=Payment.Source.MOBILE_MONEY,
            gateway_initiated_at__lte=stale_threshold,
        )
        .exclude(provider_code="")
        .order_by("gateway_initiated_at")[:batch_size]
    )

    summary = {
        "checked": 0, "valide": 0, "rejete": 0,
        "still_pending": 0, "timed_out": 0, "errors": 0, "rate_limited": 0,
    }

    for idx, payment in enumerate(base_qs):
        # 24h écoulées → abandon quelle que soit la réponse du provider.
        if payment.gateway_initiated_at and payment.gateway_initiated_at <= timeout_threshold:
            with transaction.atomic():
                payment.statut = Payment.Statut.REJETE
                payment.motif_rejet = "Timeout — aucune confirmation sous 24h."
                payment.save(update_fields=["statut", "motif_rejet", "updated_at"])
                summary["timed_out"] += 1
            continue

        if idx > 0:
            time.sleep(INTER_CALL_DELAY)

        summary["checked"] += 1
        try:
            provider = get_provider(payment.provider_code)
            current = provider.check_status(payment)
        except (ProviderError, ValueError) as exc:
            if "TOO_MANY_REQUESTS" in str(exc):
                logger.info("Tara throttle sur Payment #%s — pause %ss", payment.id, RATE_LIMIT_RETRY_DELAY)
                time.sleep(RATE_LIMIT_RETRY_DELAY)
                try:
                    current = provider.check_status(payment)
                except (ProviderError, ValueError) as exc2:
                    logger.warning("Reconcile retry KO Payment #%s: %s", payment.id, exc2)
                    summary["rate_limited"] += 1
                    continue
            else:
                logger.warning("Reconcile KO Payment #%s: %s", payment.id, exc)
                summary["errors"] += 1
                continue

        if current == "valide":
            try:
                handle_webhook_event(payment.idempotency_key, "valide")
                summary["valide"] += 1
            except Exception:  # noqa: BLE001
                logger.exception("handle_webhook_event KO Payment #%s", payment.id)
                summary["errors"] += 1
        elif current == "rejete":
            try:
                handle_webhook_event(payment.idempotency_key, "rejete")
                summary["rejete"] += 1
            except Exception:  # noqa: BLE001
                logger.exception("handle_webhook_event KO Payment #%s", payment.id)
                summary["errors"] += 1
        else:
            summary["still_pending"] += 1

    logger.info("reconcile_pending_payments summary=%s", summary)
    return summary


def reconcile_pending_payments_scheduled() -> dict:
    """Wrapper zéro-argument pour un ordonnanceur (django-q2 / cron)."""
    return reconcile_pending_payments()
