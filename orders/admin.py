from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("line_total",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    inlines = [OrderItemInline]
    list_display = (
        "reference", "customer_name", "phone", "city",
        "total", "channel", "status", "created_at",
    )
    list_filter = ("status", "channel", "created_at")
    list_editable = ("status",)
    search_fields = ("reference", "customer_name", "phone")
    readonly_fields = ("reference", "created_at", "updated_at", "total")
    date_hierarchy = "created_at"
