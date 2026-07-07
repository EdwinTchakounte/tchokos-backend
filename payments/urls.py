"""Routes paiements — montées sous ``/api/payments/`` par api/urls.py."""
from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("webhook/tara/", views.webhook_tara, name="webhook-tara"),
    path("status/", views.payment_status, name="status"),
    # Simulateur dev — renvoie 404 quand DEBUG=False.
    path("dev/<str:ref>/confirm/", views.dev_confirm_payment, name="dev-confirm"),
]
