from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id", "order", "montant", "statut", "source",
        "provider_code", "reference_externe", "created_at", "date_validation",
    )
    list_filter = ("statut", "source", "provider_code", "created_at")
    search_fields = (
        "order__reference", "reference_externe", "phone",
        "idempotency_key", "order__customer_name",
    )
    readonly_fields = (
        "idempotency_key", "reference_externe", "gateway_initiated_at",
        "date_validation", "created_at", "updated_at",
    )
    autocomplete_fields = ()
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
