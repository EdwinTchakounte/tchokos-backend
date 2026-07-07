"""Réconciliation manuelle des Payment Tara ``en_attente``.

Usage :
    python manage.py reconcile_payments
    python manage.py reconcile_payments --payment-id 12 --force-valide

Le cron fait ce travail automatiquement ; cette commande sert à déclencher
maintenant, ou à forcer la validation d'un Payment précis quand MoMo a débité
mais que Tara n'a jamais envoyé de webhook (``--force-valide``).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from payments.models import Payment
from payments.services import handle_webhook_event
from payments.tasks import reconcile_pending_payments


class Command(BaseCommand):
    help = "Réconcilie les paiements Tara en attente (poll statut, applique si changé)."

    def add_arguments(self, parser):
        parser.add_argument("--payment-id", type=int, default=None,
                            help="Force la réconciliation d'un Payment précis.")
        parser.add_argument("--force-valide", action="store_true",
                            help="Avec --payment-id : force le passage à valide.")
        parser.add_argument("--batch-size", type=int, default=200)

    def handle(self, *args, **opts):
        if opts.get("payment_id") and opts.get("force_valide"):
            try:
                payment = Payment.objects.get(pk=opts["payment_id"])
            except Payment.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Payment #{opts['payment_id']} introuvable."))
                return
            if payment.statut != Payment.Statut.EN_ATTENTE:
                self.stderr.write(self.style.WARNING(
                    f"Payment #{payment.id} déjà en {payment.statut!r} — rien à faire."))
                return
            self.stdout.write(
                f"Forçage VALIDE sur Payment #{payment.id} "
                f"({payment.montant} FCFA, commande {payment.order.reference})…")
            handle_webhook_event(
                payment.idempotency_key,
                "valide",
                provider_reference=payment.reference_externe or "",
                raw_payload={"manual_reconcile": True, "command": "reconcile_payments"},
            )
            payment.refresh_from_db()
            self.stdout.write(self.style.SUCCESS(f"Payment #{payment.id} → {payment.statut}"))
            return

        summary = reconcile_pending_payments(batch_size=opts["batch_size"])
        self.stdout.write(self.style.SUCCESS(f"reconcile_pending_payments → {summary}"))
