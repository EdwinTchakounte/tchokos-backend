"""Traitement périodique des livraisons (à lancer chaque soir, ex: via cron).

1. Expire les courses assignées dont la fenêtre de 4h est dépassée sans
   acceptation (→ statut EXPIRED, signalées au service).
2. Compile toutes les livraisons « à vérifier » (non validées) et les remonte
   au numéro service de la plateforme (rapport loggé + email Brevo si configuré).

Usage : python manage.py process_deliveries
À planifier le soir : 0 21 * * *  (21h)
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from delivery.models import Delivery
from siteconfig.models import BrandSettings
from integrations import brevo


class Command(BaseCommand):
    help = "Expire les courses en retard et remonte les livraisons non validées au service."

    def handle(self, *args, **options):
        # 1. Expiration des courses non acceptées dans les 4h
        expired = 0
        for d in Delivery.objects.filter(status=Delivery.Status.ASSIGNED):
            if d.is_overdue:
                d.expire()
                expired += 1
        self.stdout.write(f"Courses expirées (>4h) : {expired}")

        # 2. Rapport des livraisons à vérifier
        to_review = (
            Delivery.objects.filter(flagged_for_review=True, reviewed=False)
            .select_related("order", "courier", "zone")
        )
        count = to_review.count()
        if not count:
            self.stdout.write(self.style.SUCCESS("Aucune livraison à vérifier ce soir."))
            return

        lines = []
        for d in to_review:
            lines.append(
                f"- {d.order.reference} | {d.order.customer_name} {d.order.phone} "
                f"| zone {d.zone.name if d.zone else '—'} "
                f"| livreur {d.courier.name if d.courier else 'non assigné'} "
                f"| statut {d.get_status_display()}"
            )
        report = "\n".join(lines)

        service = getattr(settings, "PLATFORM_SERVICE_PHONE", "")
        self.stdout.write(
            self.style.WARNING(
                f"\n=== {count} livraison(s) à vérifier — numéro service {service or '(non configuré)'} ===\n"
                f"{report}"
            )
        )

        # Email au service via Brevo (best-effort)
        brand = BrandSettings.load()
        if brand.email:
            try:
                brevo.send_email(
                    to_email=brand.email,
                    to_name=brand.site_name,
                    subject=f"[Service] {count} livraison(s) à vérifier ce soir",
                    html_content="<h3>Livraisons non validées</h3><ul>"
                    + "".join(f"<li>{l[2:]}</li>" for l in lines)
                    + "</ul>",
                )
                self.stdout.write("Rapport envoyé au service par email.")
            except brevo.BrevoError:
                self.stderr.write("Échec de l'envoi email du rapport.")
