from django.contrib import admin

from .models import Vendor


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("shop_name", "name", "phone", "is_active")
    list_editable = ("is_active",)
    search_fields = ("shop_name", "name", "phone")
