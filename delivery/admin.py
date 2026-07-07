from django.contrib import admin, messages

from .models import DeliveryZone, Courier, Delivery, Settlement


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "fee", "eta_minutes", "order", "is_active")
    list_editable = ("fee", "eta_minutes", "order", "is_active")
    list_filter = ("city", "is_active")
    search_fields = ("name",)


@admin.register(Courier)
class CourierAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "is_active", "is_available")
    list_editable = ("is_active", "is_available")
    list_filter = ("is_active", "is_available", "zones")
    search_fields = ("name", "phone")
    filter_horizontal = ("zones",)


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "order", "zone", "courier", "status",
        "acceptance_deadline", "delivery_code", "flagged_for_review",
    )
    list_filter = ("status", "flagged_for_review", "reviewed", "zone")
    search_fields = ("order__reference", "order__customer_name", "delivery_code")
    autocomplete_fields = ("order", "courier")
    readonly_fields = (
        "assigned_at", "acceptance_deadline", "accepted_at",
        "completed_at", "delivery_code", "created_at", "updated_at",
    )
    actions = ("action_assign", "action_expire_overdue", "action_mark_reviewed")

    @admin.action(description="Démarrer la course (assigner — délai 4h)")
    def action_assign(self, request, queryset):
        done = 0
        for d in queryset:
            if d.courier and d.status == Delivery.Status.PENDING:
                d.assign(d.courier)
                done += 1
        if done:
            self.message_user(request, f"{done} course(s) assignée(s) (4h).")
        else:
            self.message_user(
                request,
                "Renseignez d'abord un livreur sur des livraisons « À assigner ».",
                level=messages.WARNING,
            )

    @admin.action(description="Marquer expirées (délai 4h dépassé)")
    def action_expire_overdue(self, request, queryset):
        n = 0
        for d in queryset:
            if d.is_overdue:
                d.expire()
                n += 1
        self.message_user(request, f"{n} course(s) expirée(s) et signalée(s) au service.")

    @admin.action(description="Marquer comme vérifiées (service)")
    def action_mark_reviewed(self, request, queryset):
        n = queryset.update(reviewed=True, flagged_for_review=False)
        self.message_user(request, f"{n} livraison(s) marquée(s) vérifiées.")


@admin.register(Settlement)
class SettlementAdmin(admin.ModelAdmin):
    list_display = (
        "delivery", "courier", "direction", "amount", "collected",
        "courier_fee", "is_cod", "status", "settled_at",
    )
    list_filter = ("status", "direction", "is_cod")
    search_fields = ("delivery__order__reference", "courier__name")
    readonly_fields = ("created_at", "updated_at", "settled_at")
    actions = ("action_mark_settled",)

    @admin.action(description="Marquer comme réglé")
    def action_mark_settled(self, request, queryset):
        n = 0
        for s in queryset.filter(status=Settlement.Status.PENDING):
            s.mark_settled()
            n += 1
        self.message_user(request, f"{n} décaissement(s) réglé(s).")
