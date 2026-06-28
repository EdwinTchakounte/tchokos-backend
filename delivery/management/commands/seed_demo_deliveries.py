"""Crée des courses de démonstration assignées à un livreur, dans plusieurs
états (à accepter / acceptée avec code / livrée), pour illustrer l'espace livreur.

Idempotent (références préfixées DEMO). Usage : python manage.py seed_demo_deliveries
"""
from django.core.management.base import BaseCommand

from catalog.models import Product
from orders.models import Order, OrderItem
from delivery.models import Courier, DeliveryZone, Delivery


class Command(BaseCommand):
    help = "Courses de démo pour l'espace livreur."

    def handle(self, *args, **options):
        courier = Courier.objects.filter(zones__isnull=False).first()
        if not courier:
            self.stderr.write("Aucun livreur. Lancez d'abord seed_delivery.")
            return
        zone = courier.zones.first()
        products = list(Product.objects.filter(is_active=True)[:4])
        if not products:
            self.stderr.write("Aucun produit. Lancez d'abord seed_demo.")
            return

        demos = [
            ("DEMO-A1", "Awa Ngono", "237699111222", "assign"),
            ("DEMO-A2", "Brice Talla", "237699333444", "assign"),
            ("DEMO-B1", "Carine Foko", "237699555666", "accept"),
            ("DEMO-C1", "Daniel Owona", "237699777888", "complete"),
        ]

        for ref, name, phone, target_state in demos:
            if Order.objects.filter(reference=f"TCH-{ref}").exists():
                continue
            order = Order.objects.create(
                reference=f"TCH-{ref}",
                customer_name=name,
                phone=phone,
                city=zone.name,
                address=f"{zone.name}, près du carrefour",
                delivery_fee=zone.fee,
                channel=Order.Channel.WHATSAPP,
            )
            p = products[hash(ref) % len(products)]
            OrderItem.objects.create(
                order=order, product=p, product_name=p.name,
                unit_price=p.price, quantity=1, size="42",
            )
            order.recompute_total()
            order.save(update_fields=["total"])

            d = Delivery.objects.create(order=order, zone=zone)
            d.assign(courier)  # → ASSIGNED (fenêtre 4h)
            if target_state in ("accept", "complete"):
                code = d.accept()  # → ACCEPTED + code
                if target_state == "complete":
                    d.complete_with_code(code)  # → COMPLETED + commande livrée
            self.stdout.write(f"  + course {ref} [{d.get_status_display()}] → {courier.name}")

        self.stdout.write(self.style.SUCCESS(
            f"Courses de démo prêtes pour {courier.name} ({courier.phone})."
        ))
